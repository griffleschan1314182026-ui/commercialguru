-- CommercialGuru listings schema for Supabase (Postgres).
-- Run once in the Supabase SQL editor.
--
-- Design: one row per listing (latest state) plus a price_history row only
-- when a price changes, so storage stays small (~30k listings, well inside
-- the 500 MB free tier) instead of growing by ~30k rows every day.

create table if not exists listings (
  listing_id      bigint primary key,
  listing_type    text not null check (listing_type in ('sale', 'rent')),
  url             text not null,
  title           text,
  price_sgd       numeric,            -- sale price, or monthly rent for 'rent'
  floor_area_sqft numeric,
  psf_sgd         numeric,            -- per sqft (per month for rent)
  property_type   text,
  location        text,               -- CommercialGuru district group, e.g. 'Chinatown / Tanjong Pagar'
  tenure          text,
  agency          text,
  posted_on       date,
  first_seen      date not null default current_date,
  last_seen       date not null default current_date
);

create index if not exists listings_type_seen on listings (listing_type, last_seen);
create index if not exists listings_ptype on listings (property_type);

create table if not exists price_history (
  listing_id bigint references listings (listing_id) on delete cascade,
  seen_on    date not null default current_date,
  price_sgd  numeric,
  primary key (listing_id, seen_on)
);

create table if not exists scrape_runs (
  id           bigint generated always as identity primary key,
  listing_type text not null,
  status       text not null,          -- running | complete | partial | failed
  pages        int,
  listings     int,
  error        text,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz
);

-- Record a price point on first insert and whenever the price changes.
create or replace function record_price() returns trigger language plpgsql
set search_path = public as $$
begin
  if tg_op = 'INSERT' or new.price_sgd is distinct from old.price_sgd then
    insert into price_history (listing_id, seen_on, price_sgd)
    values (new.listing_id, current_date, new.price_sgd)
    on conflict (listing_id, seen_on) do update set price_sgd = excluded.price_sgd;
  end if;
  return new;
end $$;

drop trigger if exists listings_price on listings;
create trigger listings_price after insert or update of price_sgd on listings
  for each row execute function record_price();

-- A listing is active if it was seen on the latest *complete* run for its type,
-- so a failed or partial run never makes listings look delisted.
create or replace view listings_current with (security_invoker = on) as
select l.*,
       l.last_seen >= coalesce(r.last_complete, l.last_seen) as is_active
from listings l
left join (
  select listing_type, max(finished_at)::date as last_complete
  from scrape_runs where status = 'complete' group by listing_type
) r using (listing_type);

-- Daily summary for trend charts.
create or replace view daily_stats with (security_invoker = on) as
select listing_type, seen_on, count(*) as price_points,
       percentile_cont(0.5) within group (order by price_history.price_sgd) as median_price
from price_history join listings using (listing_id)
group by listing_type, seen_on;

-- Read-only public access for the dashboard (anon key). Writes need the
-- service-role key, which only the GitHub Action holds.
alter table listings      enable row level security;
alter table price_history enable row level security;
alter table scrape_runs   enable row level security;

drop policy if exists "read listings" on listings;
create policy "read listings" on listings for select to anon, authenticated using (true);
drop policy if exists "read history" on price_history;
create policy "read history" on price_history for select to anon, authenticated using (true);
drop policy if exists "read runs" on scrape_runs;
create policy "read runs" on scrape_runs for select to anon, authenticated using (true);
