import hashlib
import json
import sys

from vehicle_search.seed import build, main
from vehicle_search.storage import connect


def test_seed_build_is_reproducible():
    first = [v.__dict__ for v in build(300, 42)]
    second = [v.__dict__ for v in build(300, 42)]
    assert first == second
    assert hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest() == "9a44a8e6b29369db77db40187a52f0231999090d6b6c5c6fa8ee954724c4658a"


def test_seed_noop_and_reset(tmp_path, monkeypatch, capsys):
    db = tmp_path / "catalogue.db"
    monkeypatch.setattr(sys, "argv", ["vehicle-seed", "--count", "8", "--seed", "7", "--db", str(db)])
    main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["vehicle-seed", "--count", "9", "--seed", "8", "--db", str(db)])
    main()
    assert "already seeded" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["vehicle-seed", "--count", "9", "--seed", "8", "--db", str(db), "--reset"])
    main()
    capsys.readouterr()
    conn = connect(str(db), read_only=True)
    assert conn.execute("SELECT count(*) FROM vehicles").fetchone()[0] == 9
    conn.close()
