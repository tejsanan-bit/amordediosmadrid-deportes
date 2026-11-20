-- Pegar entero en Supabase > SQL Editor > Run
create table equipos(id bigint generated always as identity primary key, nombre text not null, slug text unique not null,
  deporte_id int, competicion_id int, categoria_id int, grupo_id int);
create table jugadores(id bigint generated always as identity primary key, iniciales text not null, dorsal int,
  familia text not null, un_adulto bool default false);
create table inscripciones(jugador_id bigint references jugadores on delete cascade,
  equipo_id bigint references equipos on delete cascade, prioridad int default 1, primary key(jugador_id, equipo_id));
create table asistencias(jugador_id bigint references jugadores on delete cascade, partido_id bigint, estado text,
  primary key(jugador_id, partido_id));
create table externos(id bigint generated always as identity primary key, jugador_id bigint references jugadores on delete cascade,
  deporte text, titulo text, inicio timestamp, duracion_min int default 60, lugar text, en_colegio bool default false,
  pres_min int default 30, desp_min int default 15, margen_min int default 15);
-- Seguridad: nadie puede leer las tablas desde fuera; solo la web con la clave secreta (service_role)
alter table equipos enable row level security; alter table jugadores enable row level security;
alter table inscripciones enable row level security; alter table asistencias enable row level security;
alter table externos enable row level security;
