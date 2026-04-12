import threading

class CoreAllocator:
    def __init__(self, core_ids: list[int]):
        self._available = list(core_ids)
        self._condition = threading.Condition()

    def request(self, count: int) -> list[int]:
        with self._condition:
            while len(self._available) < count:
                self._condition.wait()
            return [self._available.pop() for _ in range(count)]

    def release(self, cores: list[int]):
        if not cores:
            return
        with self._condition:
            self._available.extend(cores)
            self._condition.notify_all()