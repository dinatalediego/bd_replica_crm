-- Medallio Pocket PROD privacy/security audit.
-- Expected result for the first query: ZERO rows.

select table_schema, table_name, column_name
from information_schema.columns
where table_schema = 'public'
  and table_name like 'pocket_%'
  and lower(column_name) ~
      '(cliente|client|lead|dni|document|telefono|phone|celular|correo|email|direccion|address|nota|note|coment|conversation|grabacion|recording|proforma|unidad|asesor)'
order by table_name, ordinal_position;

-- RLS must be enabled for every mobile table.
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename like 'pocket_%'
order by tablename;

-- anon must have no table privileges.
select grantee, table_name, privilege_type
from information_schema.role_table_grants
where grantee = 'anon'
  and table_schema = 'public'
  and table_name like 'pocket_%'
order by table_name, privilege_type;

-- Only SELECT should be granted to authenticated.
select grantee, table_name, privilege_type
from information_schema.role_table_grants
where grantee = 'authenticated'
  and table_schema = 'public'
  and table_name like 'pocket_%'
order by table_name, privilege_type;

-- There must be one SELECT policy per mobile table (pocket_access has its own self policy).
select tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
  and tablename like 'pocket_%'
order by tablename, policyname;
