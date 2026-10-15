from __future__ import annotations
import argparse
import hashlib
from importlib.resources import files
import os
from pathlib import Path

from .archive import atomic_write, build_archive, read_archive
from .contracts import PackError, canonical, strict_load
from .factory import build_products, demo_snapshot


def builder_hash():
    root=files('replica_cygnus.publishing')
    paths=list(root.glob('*.py'))+list(root.joinpath('schemas').glob('*.json'))
    h=hashlib.sha256()
    for path in sorted(paths,key=str):
        h.update(path.name.encode()); h.update(b'\0'); h.update(path.read_bytes())
    return h.hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description='Medallio analytical products: offline and private by default')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('demo','build'):
        p=sub.add_parser(name)
        p.add_argument('--output',type=Path,required=True)
        p.add_argument('--generated-at',required=True,help='Explicit ISO timestamp for reproducible bytes')
        p.add_argument('--git-commit',required=True)
        if name=='build': p.add_argument('--snapshot',type=Path,required=True)
    p=sub.add_parser('validate'); p.add_argument('pack',type=Path)
    p=sub.add_parser('capture'); p.add_argument('--as-of',required=True); p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('record-decision'); p.add_argument('--event',type=Path,required=True)
    p=sub.add_parser('register'); p.add_argument('pack',type=Path)
    p=sub.add_parser('preview'); p.add_argument('pack',type=Path); p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command in ('demo','build'):
            snap=demo_snapshot() if args.command=='demo' else strict_load(args.snapshot.read_bytes())
            packs=build_products(snap,generated_at=args.generated_at)
            raw=build_archive(packs,git_commit=args.git_commit,builder_sha256=builder_hash())
            read_archive(raw)
            atomic_write(args.output,raw)
            atomic_write(args.output.with_suffix('.sha256'),(hashlib.sha256(raw).hexdigest()+'  '+args.output.name+'\n').encode())
            print(f'Created {args.output.name}; {packs["data"]["label"]}')
        elif args.command=='record-decision':
            import psycopg
            from .local import record_decision_event
            event=strict_load(args.event.read_bytes())
            with psycopg.connect(os.environ['MEDALLIO_PUBLISH_DSN'],connect_timeout=10) as conn:
                record_decision_event(conn,event)
            print('Private decision feedback recorded; no causal claim implied')
        elif args.command=='capture':
            import psycopg
            from .local import capture_snapshot
            with psycopg.connect(os.environ['MEDALLIO_PUBLISH_DSN'],connect_timeout=10) as conn:
                snapshot=capture_snapshot(conn,args.as_of)
            atomic_write(args.output,canonical(snapshot)); print('Private local snapshot captured')
        else:
            manifest,packs=read_archive(args.pack.read_bytes())
            if args.command=='register':
                import psycopg
                from .local import register_bundle
                with psycopg.connect(os.environ['MEDALLIO_PUBLISH_DSN'],connect_timeout=10) as conn:
                    register_bundle(conn,manifest,packs,hashlib.sha256(args.pack.read_bytes()).hexdigest())
                print('Registered immutable local release')
            elif args.command=='preview':
                from .preview import render
                atomic_write(args.output,render(packs).encode()); print('Offline preview created')
            else: print('Valid: schemas, references, calculations and SHA-256 integrity')
        return 0
    except (PackError,ValueError,OSError,KeyError) as exc:
        # Avoid displaying data/DSN values. DB diagnostics are kept off public output.
        parser.exit(2,f'Operation rejected ({type(exc).__name__}). Check input contract and local configuration.\n')
    except Exception as exc:
        if type(exc).__module__.startswith('psycopg'):
            parser.exit(2,'Database operation rejected. Check local connection, schema and evidence references.\n')
        raise


if __name__=='__main__':
    raise SystemExit(main())
