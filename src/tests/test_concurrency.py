"""AT-12: two simultaneous submits for the last unit, on separate connections."""
import threading

from core.rules import BusinessRuleError
from helpers import MAIN, available, place


def test_at12_exactly_one_submit_wins_the_last_unit():
    place(MAIN, "13:00", {"Fruit Bowl": 5})
    assert available(MAIN, "13:00", "Fruit Bowl") == 1

    barrier = threading.Barrier(2)
    results = []

    def worker(customer):
        barrier.wait()
        try:
            place(MAIN, "13:00", {"Fruit Bowl": 1}, customer=customer, name=customer)
            results.append("ok")
        except BusinessRuleError:
            results.append("refused")

    threads = [threading.Thread(target=worker, args=(c,)) for c in ("S1", "S2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["ok", "refused"]
    assert available(MAIN, "13:00", "Fruit Bowl") == 0
