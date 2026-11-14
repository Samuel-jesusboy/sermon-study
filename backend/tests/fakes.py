"""A small in-memory stand-in for the PostgREST client, enough for the queries the app makes."""
import copy
import itertools
import uuid
from datetime import datetime, timezone


class Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class Query:
    def __init__(self, db, table):
        self.db, self.table_name = db, table
        self.filters, self.op, self.payload = [], "select", None
        self._order, self._limit, self._range, self._count = None, None, None, None
        self._negate = False

    # building
    def select(self, cols="*", count=None):
        self.op, self._count = "select", count
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    @property
    def not_(self):
        self._negate = True
        return self

    def _add(self, fn):
        neg = self._negate
        self._negate = False
        self.filters.append((lambda r: not fn(r)) if neg else fn)
        return self

    def eq(self, k, v):
        return self._add(lambda r: r.get(k) == v)

    def neq(self, k, v):
        return self._add(lambda r: r.get(k) != v)

    def in_(self, k, vs):
        return self._add(lambda r: r.get(k) in vs)

    def gte(self, k, v):
        return self._add(lambda r: str(r.get(k, "")) >= str(v))

    def contains(self, k, vs):
        return self._add(lambda r: all(x in (r.get(k) or []) for x in vs))

    def is_(self, k, v):
        return self._add(lambda r: r.get(k) is None if v == "null" else r.get(k) == v)

    def or_(self, expr):
        return self  # not modelled; tests don't depend on it

    def order(self, k, desc=False):
        self._order = (k, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    # running
    def _rows(self):
        return self.db.tables.setdefault(self.table_name, [])

    def _match(self):
        return [r for r in self._rows() if all(f(r) for f in self.filters)]

    def execute(self):
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in items:
                row = self.db.defaults(self.table_name)
                row.update(copy.deepcopy(item))
                self._rows().append(row)
                out.append(copy.deepcopy(row))
            return Result(out)
        if self.op == "update":
            out = []
            for r in self._match():
                r.update(copy.deepcopy(self.payload))
                r["updated_at"] = datetime.now(timezone.utc).isoformat()
                out.append(copy.deepcopy(r))
            return Result(out)
        if self.op == "delete":
            matched = self._match()
            self.db.tables[self.table_name] = [r for r in self._rows() if r not in matched]
            return Result(copy.deepcopy(matched))
        rows = self._match()
        if self._order:
            k, desc = self._order
            rows = sorted(rows, key=lambda r: (r.get(k) is None, r.get(k)), reverse=desc)
        if self._range:
            rows = rows[self._range[0]:self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        out = []
        for r in rows:
            row = copy.deepcopy(r)
            if self.table_name == "jobs":
                for key in ("source", "video_id", "filename", "church_name"):
                    row.setdefault(key, (r.get("input") or {}).get(key))
            out.append(row)
        return Result(out, count=len(out) if self._count else None)


class RPC:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    def execute(self):
        handler = self.db.rpc_handlers.get(self.name)
        return Result(handler(self.params) if handler else [])


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list] = {}
        self.rpc_handlers = {}
        self._ids = itertools.count(1)

    def defaults(self, table):
        now = datetime.now(timezone.utc).isoformat()
        row = {"created_at": now}
        if table == "sermon_chunks":
            row["id"] = next(self._ids)
        else:
            row["id"] = str(uuid.uuid4())
        if table == "jobs":
            row["updated_at"] = now
        if table == "sermons":
            row.setdefault("is_public", False)
        return row

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, params):
        return RPC(self, name, params)
