from javscraper.providers.avbase import AVBaseProvider
from javscraper.providers.avmoo import AVMOOProvider
from javscraper.providers.freejavbt import FreeJavBTProvider
from javscraper.providers.jav321 import JAV321Provider
from javscraper.providers.javbooks import JavBooksProvider
from javscraper.providers.javbus import JavBusProvider
from javscraper.providers.javdb import JavDBProvider


PROVIDER_CLASSES = {
    "AVBASE": AVBaseProvider,
    "JavBus": JavBusProvider,
    "JAV321": JAV321Provider,
    "JavDB": JavDBProvider,
    "AVMOO": AVMOOProvider,
    "FreeJavBT": FreeJavBTProvider,
    "JavBooks": JavBooksProvider,
}
