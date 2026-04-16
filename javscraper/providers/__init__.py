from javscraper.providers.avbase import AVBaseProvider
from javscraper.providers.avmoo import AVMOOProvider
from javscraper.providers.fc2 import FC2Provider
from javscraper.providers.freejavbt import FreeJavBTProvider
from javscraper.providers.jav321 import JAV321Provider
from javscraper.providers.javbooks import JavBooksProvider
from javscraper.providers.javbus import JavBusProvider
from javscraper.providers.javdb import JavDBProvider
from javscraper.providers.muramura import MuramuraProvider
from javscraper.providers.onepondo import OnePondoProvider
from javscraper.providers.pacopacomama import PacopacomamaProvider
from javscraper.providers.tenmusume import TenMusumeProvider


PROVIDER_CLASSES = {
    "AVBASE": AVBaseProvider,
    "JavBus": JavBusProvider,
    "JAV321": JAV321Provider,
    "FC2": FC2Provider,
    "1Pondo": OnePondoProvider,
    "10musume": TenMusumeProvider,
    "PACOPACOMAMA": PacopacomamaProvider,
    "MURAMURA": MuramuraProvider,
    "JavDB": JavDBProvider,
    "AVMOO": AVMOOProvider,
    "FreeJavBT": FreeJavBTProvider,
    "JavBooks": JavBooksProvider,
}
