# PostgreSQL Schema Standards

Standards for designing PostgreSQL schemas. They cover the target schema, not the migration tool. Follow the project's
own migration workflow.

## Normalization

- Start normalized, typically to third normal form. Redundant data is data that can disagree with itself
- Denormalize only for a measured problem (see "When to Denormalize")

## Data Types

- Timestamps: `timestamptz`, never `timestamp`. A timestamp without a zone is ambiguous once two servers disagree
- Strings: `text`, unless the domain has a real length limit. `varchar(n)` with an arbitrary `n` buys nothing
- JSON: `jsonb`, never `json` or `text`. `jsonb` can be indexed and queried
- Identifiers: `bigint` for internal keys. `uuid` when IDs must be unique across systems or unguessable
- Numbers: `integer` or `bigint` by range. `numeric` for exact decimals such as money; never floating point there
- Flags: `boolean`, never an integer or a string

## Constraints Live in the Database

The database enforces integrity. Application code can be bypassed by a script, a second service, or a bug.

- Every table has a primary key
- Every relationship has a foreign key
- `NOT NULL` wherever a null has no meaning
- `CHECK` for business rules, such as a positive quantity or a closed set of status values
- `UNIQUE` for natural keys

## Relationships

- One-to-many: a foreign key in the "many" table
- Many-to-many: a junction table with a foreign key to each side, and a composite primary key over both
- One-to-one: a foreign key with a `UNIQUE` constraint. Merge the tables instead if their lifecycles are identical
- Never a polymorphic foreign key (`owner_type` plus `owner_id`). The database cannot enforce it. Use one junction
  table per target type

## Indexes

Index for the queries the code actually runs, not for every column.

- Primary keys are indexed automatically. Foreign keys are not. Index a foreign key column used in joins or cascades
- Index columns used in `WHERE`, `ORDER BY`, and `GROUP BY` on hot queries
- Use a composite index when queries filter on several columns together. Put equality columns before range columns
- Use a partial index when queries only ever touch a subset, such as `WHERE deleted_at IS NULL`
- Confirm an index is used with `EXPLAIN ANALYZE` on realistic data

## When to Denormalize

Denormalization trades write complexity and consistency risk for read speed. Make that trade only with evidence.

Valid reasons:

- A measured performance problem
- A read-heavy workload where the extra write cost is acceptable
- An aggregate too expensive to compute per request
- Data that is immutable once written, such as audit logs or time series

Invalid reasons:

- "It might be faster," without a measurement
- Avoiding joins. Indexed joins are not slow
- Convenience in application code

When you denormalize, record the measured problem, how the copies are kept in sync, and why the cost is worth it.
