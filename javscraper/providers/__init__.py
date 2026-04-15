from javscraper.providers.avmoo import AVMOOProvider
from javscraper.providers.freejavbt import FreeJavBTProvider
from javscraper.providers.javbooks import JavBooksProvider
from javscraper.providers.javbus import JavBusProvider
from javscraper.providers.javdb import JavDBProvider


PROVIDER_CLASSES = {
    "JavBus": JavBusProvider,
    "JavDB": JavDBProvider,
    "AVMOO": AVMOOProvider,
    "FreeJavBT": FreeJavBTProvider,
    "JavBooks": JavBooksProvider,
}
