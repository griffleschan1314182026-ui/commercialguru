-- 002: listing history. Run once in the Supabase SQL editor (safe to re-run).
--
-- Adds:
--   * listings.delisted_on   - the day a listing stopped appearing on the site
--   * listing_changes        - one row per event: listed, delisted, relisted,
--                              or a change to title / price / area / type /
--                              location / tenure / agency (old -> new value)
--   * mark_delisted()        - called by the scraper after each complete run
-- Past listings are never deleted; they keep their last known details.

alter table listings add column if not exists delisted_on date;

create table if not exists listing_changes (
  id         bigint generated always as identity primary key,
  listing_id bigint not null references listings (listing_id) on delete cascade,
  changed_on date not null default (now() at time zone 'Asia/Singapore')::date,
  field      text not null,   -- listed | delisted | relisted | <column name>
  old_value  text,
  new_value  text
);
-- Dates follow Singapore time (the scraper runs in the early morning SGT,
-- which is still the previous day in UTC).
alter table listing_changes alter column changed_on set default (now() at time zone 'Asia/Singapore')::date;
alter table price_history alter column seen_on set default (now() at time zone 'Asia/Singapore')::date;

create or replace function record_price() returns trigger language plpgsql
set search_path = public as $$
begin
  if tg_op = 'INSERT' or new.price_sgd is distinct from old.price_sgd then
    insert into price_history (listing_id, price_sgd)
    values (new.listing_id, new.price_sgd)
    on conflict (listing_id, seen_on) do update set price_sgd = excluded.price_sgd;
  end if;
  return new;
end $$;

create index if not exists listing_changes_recent on listing_changes (changed_on desc, id desc);
create index if not exists listing_changes_listing on listing_changes (listing_id);

create or replace function jsonb_to_plain_text(v jsonb) returns text language sql immutable
set search_path = public as $$
  select case when v is null or v = 'null'::jsonb then null else v #>> '{}' end
$$;

create or replace function track_listing_changes() returns trigger language plpgsql
set search_path = public as $$
declare
  f text;
  o jsonb;
  n jsonb;
begin
  if tg_op = 'INSERT' then
    insert into listing_changes (listing_id, field, new_value)
    values (new.listing_id, 'listed', new.price_sgd::text);
    return new;
  end if;

  -- Seen again after being marked delisted.
  if old.delisted_on is not null and new.last_seen > old.last_seen then
    new.delisted_on := null;
    insert into listing_changes (listing_id, field, old_value)
    values (new.listing_id, 'relisted', old.delisted_on::text);
  end if;

  foreach f in array array['title', 'price_sgd', 'floor_area_sqft', 'property_type',
                           'location', 'tenure', 'agency'] loop
    o := to_jsonb(old) -> f;
    n := to_jsonb(new) -> f;
    if n is null or n = 'null'::jsonb then
      -- The scraper missed this field today: keep the last known value.
      if o is not null and o <> 'null'::jsonb then
        new := jsonb_populate_record(new, jsonb_build_object(f, o));
      end if;
    elsif o is distinct from n then
      insert into listing_changes (listing_id, field, old_value, new_value)
      values (new.listing_id, f, jsonb_to_plain_text(o), jsonb_to_plain_text(n));
    end if;
  end loop;
  return new;
end $$;

drop trigger if exists listings_track_insert on listings;
create trigger listings_track_insert after insert on listings
  for each row execute function track_listing_changes();
drop trigger if exists listings_track_update on listings;
create trigger listings_track_update before update on listings
  for each row execute function track_listing_changes();

-- Called after a complete run: anything of that type not seen today is delisted.
create or replace function mark_delisted(p_type text, p_date date) returns integer
language sql set search_path = public as $$
  with gone as (
    update listings set delisted_on = p_date
    where listing_type = p_type and last_seen < p_date and delisted_on is null
    returning listing_id
  ), logged as (
    insert into listing_changes (listing_id, changed_on, field, old_value)
    select listing_id, p_date, 'delisted', null from gone
    returning 1
  )
  select count(*)::int from logged
$$;
revoke execute on function mark_delisted(text, date) from public, anon, authenticated;
grant execute on function mark_delisted(text, date) to service_role;

-- listings_current gains delisted_on; drop and recreate since its columns change.
drop view if exists listings_current;
create view listings_current with (security_invoker = on) as
select l.*, l.delisted_on is null as is_active
from listings l;

alter table listing_changes enable row level security;
drop policy if exists "read changes" on listing_changes;
create policy "read changes" on listing_changes for select to anon, authenticated using (true);
