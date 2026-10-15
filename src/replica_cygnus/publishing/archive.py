"""Bounded ZIP container; JSON only, integrity checked before any consumer sees it."""
from __future__ import annotations
import hashlib
import io
import os
from pathlib import Path
import tempfile
import zipfile
from .contracts import PackError, canonical, strict_load, validate, validate_bundle, MAX_JSON_BYTES

NAMES={'manifest.json','data.json','model.json','story.json','scenario.json'}
MAX_ZIP_BYTES=20_000_000


def build_archive(packs, *, git_commit, builder_sha256):
    validate_bundle(packs)
    payloads={f'{kind}.json':canonical(value) for kind,value in packs.items()}
    manifest=dict(schema_version='1.0.0',pack_id='housing-discovery',pack_version='1.0.0',
        generated_at=packs['data']['provenance']['generated_at'],classification=packs['data']['classification'],
        git_commit=git_commit,builder_sha256=builder_sha256,
        files={name:dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)) for name,raw in payloads.items()})
    validate('manifest',manifest)
    payloads['manifest.json']=canonical(manifest)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
        for name,raw in sorted(payloads.items()):
            if len(raw)>MAX_JSON_BYTES: raise PackError('Pack exceeds size budget')
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.external_attr=0o600<<16
            z.writestr(info,raw)
    return stream.getvalue()


def read_archive(raw):
    if len(raw)>MAX_ZIP_BYTES: raise PackError('Archive exceeds size budget')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            entries=z.infolist()
            if len(entries)!=5 or {e.filename for e in entries} != NAMES:
                raise PackError('Unexpected, duplicate or missing archive entry')
            for e in entries:
                if e.file_size>MAX_JSON_BYTES or e.flag_bits & 1 or e.compress_type != zipfile.ZIP_STORED:
                    raise PackError('Unsupported or oversized archive entry')
            payloads={e.filename:z.read(e) for e in entries}
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as exc:
        raise PackError('Invalid archive') from exc
    manifest=strict_load(payloads.pop('manifest.json')); validate('manifest',manifest)
    for name,raw in payloads.items():
        expected=manifest['files'][name]
        if len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
            raise PackError('Integrity mismatch')
    packs={name[:-5]:strict_load(raw) for name,raw in payloads.items()}
    validate_bundle(packs)
    if manifest['classification']!=packs['data']['classification'] or manifest['generated_at']!=packs['data']['provenance']['generated_at']:
        raise PackError('Manifest provenance mismatch')
    return manifest,packs


def atomic_write(path, raw):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(dir=path.parent,prefix='.pack-',suffix='.tmp')
    try:
        with os.fdopen(handle,'wb') as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def install_archive(raw, destination):
    """Reject corrupt updates without changing the last good installation."""
    read_archive(raw)
    atomic_write(destination,raw)
