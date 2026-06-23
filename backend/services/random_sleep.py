import logging
import random
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RandomSleep:
    base_seconds: float = 0.1
    random_seconds: float = 2.5

    def __call__(self) -> None:
        delay = self.base_seconds + self.random_seconds * random.random()
        logger.info("Random sleep: %s seconds", delay)
        time.sleep(delay)
