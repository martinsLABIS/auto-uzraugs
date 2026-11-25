"""Aprīkojuma saraksts meklējuma filtriem.

Katrai iespējai ir nosaukums lietotnē, grupa un atpazīšanas vārdi latviski, krieviski,
angliski un vāciski (portālos un sludinājumos sastopamie formulējumi).
"""
import re

GROUPS = [
    ("comfort", "Komforts"),
    ("seats", "Sēdekļi un salons"),
    ("assist", "Drošība un asistenti"),
    ("lights", "Apgaismojums"),
    ("media", "Multivide"),
    ("ev", "Elektroauto un hibrīdi"),
    ("exterior", "Ārpuse un piekare"),
    ("history", "Vēsture"),
]

EQUIPMENT = [
    # id, nosaukums, grupa, atpazīšanas regulārā izteiksme
    ("climate", "Klimata kontrole", "comfort",
     r"klimata? kontrol|klimatkontrol|klimatronik|climate control|climatronic|klimaautomatik|"
     r"\d-?zonu|divzonu|trīszonu|климат-?контрол"),
    ("keyless", "Bezatslēgas piekļuve", "comfort",
     r"keyless|bezatslēg|komfortzugang|kessy|бесключ"),
    ("tailgate", "Elektrisks bagāžnieka vāks", "comfort",
     r"bagāžnieka (aizvēr|atvēr|vāk)|el(ektr)?\w*\.? (bagāžn|aizvēr)|power tailgate|electric tailgate|"
     r"elektrische heckklappe|heckklappe,? elektrisch|easy open|virtual pedal|электропривод багаж"),
    ("aux_heater", "Autonomais sildītājs (Webasto)", "comfort",
     r"webasto|autonom\w* (sildītāj|apsild)|standheizung|auxiliary heat|parking heater|автономн\w* (отоп|подогр)"),
    ("panorama", "Panorāmas jumts", "comfort",
     r"panorām|panorama|sky ?lounge|панорам"),
    ("sunroof", "Lūka", "comfort",
     r"\blūka\b|sunroof|schiebedach|\bлюк\b"),
    ("heat_pump", "Siltumsūknis", "ev",
     r"siltumsūkn|heat ?pump|wärmepumpe|тепловой насос"),
    ("seat_heat", "Sēdekļu apsilde", "seats",
     r"sēdekļu apsild|apsildām\w* (priekš\w* )?(sēdek|krēsl)|sēdekļi ar apsildi|seat heat|heated (front )?seats|"
     r"sitzheizung|подогрев\w* сиден"),
    ("seat_vent", "Sēdekļu ventilācija", "seats",
     r"ventilē\w* (sēdek|krēsl)|sēdekļu ventil|ventilated seats|sitzbelüftung|klimatisierte sitze|вентиляц\w* сиден"),
    ("wheel_heat", "Apsildāma stūre", "seats",
     r"apsildām\w* stūr|stūres apsild|heated steering|lenkradheizung|подогрев руля"),
    ("power_seats", "Elektriski regulējami sēdekļi", "seats",
     r"el(ektr)?\w*\.? regulējam\w* (šofera |vadītāja )?(sēdek|krēsl)|el\. regulējama|power seats|electric seats|"
     r"elektrisch verstellbare? sitz|sitze,? elektrisch|memory|ar atmiņu|электрорегулиров\w* сиден"),
    ("massage", "Masāžas sēdekļi", "seats",
     r"masāž|massage|массаж"),
    ("leather", "Ādas salons", "seats",
     r"ādas (apdare|salons|sēdek|interjer)|\bāda\b|leather|\bleder|nappa|vernasca|dakota|кожан\w* салон"),
    ("seven_seats", "7 sēdvietas", "seats",
     r"\b7 (sēdviet|vietas|vietīg|seats?|sitz)|7-seat|7-sitz|sieben sitz|7 мест|3\. sēdekļu rind|third row"),
    ("acc", "Adaptīvā kruīzkontrole", "assist",
     r"adaptīv\w* kruīz|\bacc\b|adaptive cruise|distronic|abstandsregel|adaptiver tempomat|"
     r"distances kontrol|active cruise|адаптивн\w* круиз"),
    ("cruise", "Kruīza kontrole", "assist",
     r"kruīz|cruise|tempomat|круиз"),
    ("lane", "Joslu asistents", "assist",
     r"joslu (asist|turē|kontrol)|joslās|lane (assist|keep|depart)|spurhalte|spurassist|spurwechsel|"
     r"удержан\w* полос|полосы движ"),
    ("blind_spot", "Aklās zonas uzraudzība", "assist",
     r"akl\w* zon|blind ?spot|totwinkel|side assist|слеп\w* зон"),
    ("cam360", "360° kamera", "assist",
     r"360|area view|surround view|top view|vogelperspektive|bird'?s[- ]eye|кругов\w* обзор"),
    ("rear_cam", "Atpakaļskata kamera", "assist",
     r"atpakaļskata kamer|aizmugur\w* kamer|rear(view)? camera|reversing camera|rückfahrkamera|"
     r"камера заднего"),
    ("park_sensors", "Parkošanās sensori", "assist",
     r"parkošan\w* sens|parkošanās radar|park(ing)? ?(sensor|distance)|\bpdc\b|einparkhilfe|parktronic|парктроник"),
    ("auto_park", "Automātiskā parkošanās", "assist",
     r"autom\w* parkoš|park assist|parkassist|parking assistant|park pilot|self-?park|автопарков"),
    ("hud", "Head-up displejs", "assist",
     r"head[- ]?up|\bhud\b|projekcij"),
    ("night_vision", "Nakts redzamības sistēma", "assist",
     r"nakts redz|night ?vision|nachtsicht"),
    ("led", "LED priekšējie lukturi", "lights",
     r"led (luktur|priekš|gaism|headl|scheinw)|full[- ]led|led-scheinwerfer|led-hauptscheinwerfer|"
     r"led lukturi|светодиодн\w* фар"),
    ("matrix", "Matrix / lāzera / adaptīvie lukturi", "lights",
     r"matrix|laser ?light|laserlicht|pixel|multibeam|iq\.light|adaptīv\w* (luktur|gaism)|"
     r"adaptive (led|headl|light)|dynamic light|adaptiv\w* kurvenlicht"),
    ("xenon", "Ksenona lukturi", "lights",
     r"xenon|ksenon|ксенон"),
    ("nav", "Navigācija", "media",
     r"navigāc|\bnavi\b|navigation|навигац"),
    ("carplay", "Apple CarPlay / Android Auto", "media",
     r"carplay|android auto|app[- ]?connect|smartphone[- ]integr|mirror ?link"),
    ("premium_audio", "Premium audiosistēma", "media",
     r"harman|kardon|bang|b&o|bowers|burmester|meridian|\bbose\b|premium (audio|sound)|\bjbl\b|dynaudio|"
     r"canton|krell|mark levinson|focal|sennheiser"),
    ("wireless_charge", "Bezvadu telefona uzlāde", "media",
     r"bezvadu (viedier|uzlād|lād|telef)|wireless charg|induktiv\w* lad|\bqi\b|беспроводн\w* заряд"),
    ("digital_cockpit", "Digitālais mēraparātu panelis", "media",
     r"digitāl\w* (panel|instrument|mēraparāt)|virtual cockpit|digital cockpit|active info display|"
     r"live cockpit|digitales? (cockpit|kombiinstrument)"),
    ("fast_charge", "Ātrā DC uzlāde (CCS)", "ev",
     r"\bccs\b|\bdc (uzlād|lād|charg)|ātr\w* uzlād|schnelllad|fast[- ]?charg|быстр\w* заряд"),
    ("three_phase", "3 fāžu / 11 kW AC uzlāde", "ev",
     r"\b11 ?kw\b|\b22 ?kw\b|3[- ]fāz|trīsfāz|3[- ]?phas|dreiphas"),
    ("towbar", "Sakabes āķis", "exterior",
     r"sakabes āķ|\bāķis\b|tow ?bar|tow ?hitch|anhängerkupplung|\bahk\b|фаркоп"),
    ("roof_rails", "Jumta reliņi", "exterior",
     r"jumta reliņ|roof ?rails|dachreling|рейлинг"),
    ("air_susp", "Pneimopiekare", "exterior",
     r"pneimopiekar|pneimo|air suspension|airmatic|luftfederung|adaptive air|пневмо"),
    ("alloys", "Vieglmetāla diski", "exterior",
     r"vieglmetāla|alloy|leichtmetall|литые диск"),
    ("tinted", "Tonēti stikli", "exterior",
     r"tonēt|privacy glass|tinted|getönt|abgedunkelt|тонир"),
    ("sport_pack", "Sporta pakete (M Sport, S line, AMG, R-Line …)", "exterior",
     r"m[- ]?sport|s[- ]?line|\bamg\b|r[- ]?line|sport pakete|sportpaket|rs[- ]?line|st[- ]?line|gt[- ]?line|"
     r"\bfr\b|sportline|r-design|inscription"),
    ("winter_tyres", "Ziemas riepas komplektā", "exterior",
     r"ziemas riep|winter ?(tyres|tires|reifen)|winterräder|зимн\w* (шин|резин)"),
    ("service_book", "Servisa vēsture / grāmatiņa", "history",
     r"servisa (grāmat|vēstur)|service (book|history)|scheckheft|serviceheft|сервисн\w* (книж|истор)"),
    ("first_owner", "Pirmais īpašnieks", "history",
     r"pirmais īpašniek|1\. īpašniek|viens īpašniek|1\.? ?hand|first owner|one owner|erste hand|"
     r"total number of owners: 1\b|1 владел|первый владел"),
]

EQUIP_RES = {eid: re.compile(rx, re.I) for eid, _, _, rx in EQUIPMENT}


def detect_equipment(text):
    """Atgriež aprīkojuma id kopu, kas atrasti tekstā."""
    t = text or ""
    found = {eid for eid, rx in EQUIP_RES.items() if rx.search(t)}
    if "acc" in found:
        found.add("cruise")
    return found


def catalog():
    """Saraksts lietotnei."""
    return {
        "groups": [{"id": g, "name": n} for g, n in GROUPS],
        "items": [{"id": e, "name": n, "group": g} for e, n, g, _ in EQUIPMENT],
    }
