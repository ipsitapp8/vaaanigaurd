import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.tables import AuditEntry
from app.services.audit import GENESIS_HASH, append_entry, verify_chain
from app.services.evidence import sha256_hex


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def seed(session, n=4):
    for i in range(n):
        append_entry(session, "system", f"event_{i}", f"a{i}", {"tier": "HIGH", "i": i})


def test_empty_chain_valid(session):
    assert verify_chain(session) == (True, None)


def test_chain_links_and_verifies(session):
    seed(session)
    entries = session.exec(select(AuditEntry).order_by(AuditEntry.seq)).all()
    assert entries[0].prev_hash == GENESIS_HASH
    for a, b in zip(entries, entries[1:]):
        assert b.prev_hash == a.entry_hash
    assert entries[1].entry_hash == sha256_hex((entries[1].prev_hash + entries[1].payload_hash).encode())
    assert verify_chain(session) == (True, None)


@pytest.mark.parametrize("field,value", [("action", "tampered"), ("actor", "mallory"), ("analysis_id", "zzz"), ("detail_json", '{"tier":"LOW"}')])
def test_editing_a_field_is_detected(session, field, value):
    seed(session)
    e = session.exec(select(AuditEntry).where(AuditEntry.seq == 2)).one()
    setattr(e, field, value)
    session.add(e)
    session.commit()
    assert verify_chain(session) == (False, 2)


def test_rewriting_hashes_of_one_entry_breaks_the_next_link(session):
    seed(session)
    e = session.exec(select(AuditEntry).where(AuditEntry.seq == 2)).one()
    e.payload_hash = "f" * 64
    session.add(e)
    session.commit()
    assert verify_chain(session)[0] is False


def test_deleting_middle_entry_detected(session):
    seed(session)
    session.delete(session.exec(select(AuditEntry).where(AuditEntry.seq == 2)).one())
    session.commit()
    assert verify_chain(session) == (False, 3)


def test_deleting_first_entry_detected(session):
    seed(session)
    session.delete(session.exec(select(AuditEntry).where(AuditEntry.seq == 1)).one())
    session.commit()
    assert verify_chain(session) == (False, 2)
