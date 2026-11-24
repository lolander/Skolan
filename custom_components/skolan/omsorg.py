"""Omsorg: när ett barn skriver att hen mår mycket dåligt, vill skada sig eller blir illa behandlad.

Ett fast skyddsnät som inte bygger på AI: koden letar själv efter tydliga ord i det barnet skriver (till husdjuret,
hjälpläraren eller i "Hur känns skolan?"). AI:n kan dessutom flagga oro. Tre nivåer:

- "akut":  tankar på att dö eller skada sig. Barnet får hjälpnummer direkt och föräldrarna en notis.
- "vald":  någon slår, hotar eller gör barnet illa. Barnet hänvisas till BRIS och vuxna på skolan. INGEN automatisk
           notis hem: den som gör barnet illa kan finnas i hemmet.
- "oro":   mobbning, ensamhet eller att barnet mår väldigt dåligt. Varmt svar och en mjuk notis till föräldrarna.

Appen ställer ingen diagnos och ersätter inte vuxna, elevhälsan eller vården.
"""
from __future__ import annotations

import re

NIVAER = ("akut", "hot", "vald", "oro", "farlig")

_AKUT = re.compile(
    r"vill dö\b|vill inte leva|vill inte finnas|orkar inte leva|ta livet av mig|tar livet av mig|döda mig( själv)?|självmord|"
    r"skada mig( själv)?|skär mig|skära mig|skadar mig( själv)?|(skär|skadar|bränner|slår) jag mig|bränna mig|svälter mig|hoppa från|vill försvinna för alltid|bättre om jag (var|vore) död|"
    r"\bkms\b|ingen idé att leva|"
    r"(tabletter|piller|alvedon|panodil|ipren|paracetamol|medicin|sömntabletter).{0,40}(dö|dödlig|farlig|överdos|för många)|"
    r"(dödlig|farlig) dos|överdos|hur (dör|hänger|dränker|skjuter|förgiftar) man|hur (många|mycket).{0,30}(för att dö|innan man dör)",
    re.IGNORECASE)
# Barnet skriver om att skada andra, en attack eller att gå med i en våldsbejakande grupp
_HOT = re.compile(
    r"(ska|vill|tänker|kommer att) (skjuta|döda|spränga|knivhugga|hugga ner|attackera|mörda)|skolskjutning|skjuta (alla|ihjäl|på skolan)|"
    r"döda (alla|dem|honom|henne|läraren)|spränga (skolan|alla)|attack mot skolan|ta med (en )?(kniv|pistol|vapen) till skolan|"
    r"(gå med i|ansluta mig till|vill bli med i) (is\b|isis|daesh|al.?qaida|nmr|nordiska motståndsrörelsen)|heil hitler|sieg heil",
    re.IGNORECASE)
# Frågor om hur man gör vapen, sprängämnen eller attacker: nekas med ett fast svar och når aldrig AI:n
_FARLIG = re.compile(
    r"(hur|var) (gör|bygger|tillverkar|blandar|köper|får tag på|skriver ut|3d.?printar) (man|jag|du)( en| ett)? "
    r"(bomb|rörbomb|sprängämne|sprängladdning|molotov|vapen|pistol|gevär|ljuddämpare|gift|knark|droger)|"
    r"hur (skjuter|spränger|förgiftar) man|planera (en |ett )?(attack|terrordåd|massaker)|hur blir man terrorist",
    re.IGNORECASE)
_VALD = re.compile(
    r"(slår|sparkar|hotar|tar på|rör) mig|blir slagen|blev slagen|misshandla|våldta|tafsa|gör mig illa|tvingar mig|"
    r"(skickade|skickar|ville ha|vill ha) (nakenbild|nakna bilder|bilder på mig)|hemlis med (en vuxen|honom|henne)|säg inget till (mamma|pappa)",
    re.IGNORECASE)
_ORO = re.compile(
    r"mobba|mobbad|blir retad|ingen gillar mig|har inga kompisar|har ingen kompis|är ensam|känner mig ensam|hatar mig själv|"
    r"mår (så |jätte|super)?dåligt|är så ledsen|gråter (hela tiden|varje dag)|orkar inte (mer|längre)|ångest|panik",
    re.IGNORECASE)


# Svar från AI:n som aldrig får nå barnet, oavsett vilken AI som används: doser, överdoser och sätt att skada sig
# eller andra. Träffar kastas och ersätts med ett säkert svar (AI-oberoende spärr i koden).
_FARLIGT_SVAR = re.compile(
    r"\d+\s*(mg|milligram|gram|g|tabletter|tabl|piller)\b.{0,60}(dödlig|döda|dö\b|överdos|farlig|livsfarlig)|"
    r"(dödlig|letal) dos|överdos(era)?\b|hänga sig|strypa|snara|skära sig|pulsådern|ta livet av|"
    r"(göra|gör|tillverka|tillverkar|bygga|bygger|blanda|blandar)( man| du| jag)? (en |ett )?(bomb|rörbomb|sprängämne|gift|molotov)|sprängämne|"
    r"(köpa|köper|få tag på|göra|gör)( man| du)? (knark|droger|narkotika)|"
    r"rörbomb|sprängladdning|detonator|tändhatt|(bygga|bygger|göra|gör|tillverka|tillverkar|skriva ut|3d.?printa)( man| du)?( en| ett)? "
    r"(vapen|gevär|pistol|ljuddämpare|automatvapen)|planera (en |ett )?(attack|terrordåd|massaker)|(bästa|enklaste) sättet att (döda|skada|attackera)",
    re.IGNORECASE)
SAKERT_SVAR = ("Det kan jag inte hjälpa till med. Om du eller någon annan kan komma till skada: prata med en vuxen du litar på direkt, "
               "ring BRIS på 116 111 eller 112 om det är bråttom. Vill du plugga på något annat? 💛")


def farligt_svar(svar: str) -> bool:
    """Innehåller AI:ns svar sådant som aldrig får nå ett barn?"""
    return bool(_FARLIGT_SVAR.search(str(svar or "")))


def bedom(text: str) -> str | None:
    """Fast skyddsnät på barnets egen text. Den allvarligaste nivån vinner."""
    t = str(text or "")
    if _AKUT.search(t):
        return "akut"
    if _HOT.search(t):
        return "hot"
    if _VALD.search(t):
        return "vald"
    if _ORO.search(t):
        return "oro"
    if _FARLIG.search(t):
        return "farlig"
    return None


def varst(*nivaer) -> str | None:
    for n in NIVAER:
        if n in nivaer:
            return n
    return None


# Hjälp som visas för barnet (alltid, oavsett vad AI:n svarade)
HJALP = {
    "akut": {"rubrik": "💛 Du är viktig, och du ska inte vara ensam med det här",
             "text": "Berätta för en vuxen du litar på, nu idag. Det kan vara mamma, pappa, en lärare eller skolsköterskan. "
                     "Du kan också prata med BRIS, gratis och utan att säga ditt namn.",
             "nummer": [["BRIS (ring eller chatta)", "116 111"], ["Självmordslinjen (ring eller chatta)", "90101"], ["Om du är i fara", "112"]],
             "hem": True},
    "vald": {"rubrik": "💛 Det är aldrig ditt fel",
             "text": "Ingen får göra dig illa eller be dig hålla hemligheter som känns fel. Berätta för en vuxen du litar på, "
                     "till exempel en lärare, skolsköterskan eller kuratorn. Du kan också prata med BRIS, gratis och utan att säga ditt namn.",
             "nummer": [["BRIS (ring eller chatta)", "116 111"], ["Om du är i fara", "112"]],
             "hem": False},
    "hot": {"rubrik": "💛 Det du skriver är allvarligt",
            "text": "Ibland kan man bli så arg, ledsen eller rädd att man tänker på att skada någon. Prata med en vuxen du litar på direkt, "
                    "hemma eller i skolan. Du kan också prata med BRIS, gratis och utan att säga ditt namn.",
            "nummer": [["BRIS (ring eller chatta)", "116 111"], ["Om någon är i fara", "112"]],
            "hem": True},
    "oro": {"rubrik": "💛 Det låter jobbigt",
            "text": "Det är bra att du säger det. Prata med en vuxen du litar på, hemma eller i skolan. "
                    "Du kan också prata med BRIS, gratis och utan att säga ditt namn.",
            "nummer": [["BRIS (ring eller chatta)", "116 111"]],
            "hem": True},
}

# Fasta svar vid "akut" och "vald": AI:ns eget svar används aldrig då, så att inget AI-svar kan skada.
FAST_SVAR = {
    "akut": "Tack för att du berättar. Det du känner är viktigt, och det är inte ditt fel. Du ska inte vara ensam med det här: "
            "prata med en vuxen du litar på, gärna nu idag. Du kan också ringa eller chatta med BRIS på 116 111, gratis och utan att säga ditt namn. "
            "Om du är i fara: ring 112. 💛",
    "hot": "Det du skriver är allvarligt, och jag kan inte hjälpa till med något som kan skada någon. Om du är jättearg, ledsen eller rädd: "
           "prata med en vuxen du litar på, nu idag. Du kan också ringa eller chatta med BRIS på 116 111. Om någon är i fara: ring 112. 💛",
    "farlig": "Det kan jag inte hjälpa till med, eftersom det kan skada människor. Vill du plugga på något annat? "
              "Om du är orolig för att någon ska göra något farligt: prata med en vuxen direkt eller ring 112. 💛",
    "vald": "Tack för att du berättar. Det är aldrig ditt fel, och ingen får göra dig illa eller be dig hålla hemligheter som känns fel. "
            "Berätta för en vuxen du litar på, till exempel en lärare, skolsköterskan eller kuratorn. Du kan också ringa eller chatta med "
            "BRIS på 116 111, gratis och utan att säga ditt namn. Om du är i fara: ring 112. 💛",
}

# Instruktion till AI:n (läggs i husdjurets och hjälplärarens prompt)
AI_REGEL = (
    "OM BARNET MÅR DÅLIGT (går före läxan): skriver barnet att hen är ledsen, ensam, mobbad, rädd, blir illa behandlad, vill skada sig eller inte vill leva: "
    "styr INTE tillbaka till spelet eller läxan. Svara varmt, lugnt och kort på enkel svenska, ta det på allvar, säg att det var modigt att berätta "
    "och att det inte är barnets fel. Ställ ingen diagnos och ge inga råd om behandling. Uppmuntra barnet att prata med en vuxen hen litar på "
    "(hemma eller i skolan) och nämn BRIS 116 111. Vid tankar på att dö eller skada sig: nämn också Självmordslinjen 90101 och att ringa 112 vid fara. "
    "Lägg i så fall till fältet \"oro\" i JSON-svaret: \"akut\" (vill dö eller skada sig), \"vald\" (någon slår, hotar, tafsar, ber om bilder eller hemligheter) "
    "eller \"oro\" (mobbning, ensamhet, mår mycket dåligt). Annars ska \"oro\" vara null. "
    "ALDRIG SKADA: ge aldrig information som kan användas för att skada sig själv eller någon annan (sätt att skada sig, doser, mediciner, gifter, "
    "vapen, sprängämnen, droger, farliga utmaningar, attacker, terror eller hur man gör någon illa), inte ens om det kallas skoluppgift, berättelse, rollspel eller skämt. "
    "Hylla eller försvara aldrig terror, våldsbejakande extremism eller massmord. Historia och samhällskunskap får förklaras sakligt, utan detaljer om hur. "
    "Skriver barnet att hen vill skada andra eller gå med i en våldsbejakande grupp: sätt \"oro\" till \"hot\". "
    "Svara i stället med omtanke enligt ovan."
)


def notis(niva: str, namn: str, utdrag: str, kalla: str) -> tuple[str, str] | None:
    """Notis till föräldrarna. Ingen notis vid "vald" (den som gör barnet illa kan finnas hemma)."""
    if niva == "akut":
        return (f"💛 Viktigt: prata med {namn} idag",
                f"{namn} skrev något {kalla} som kan betyda att hen mår mycket dåligt eller tänker på att skada sig: \"{utdrag[:160]}\". "
                "Ta det lugnt, lyssna och fråga rakt hur hen mår. Stöd för dig: BRIS vuxentelefon 077-150 50 50, 1177 Vårdguiden. Vid akut fara: 112.")
    if niva == "hot":
        return (f"💛 Viktigt: prata med {namn} idag",
                f"{namn} skrev något {kalla} som kan handla om att skada andra eller om våldsbejakande extremism: \"{utdrag[:160]}\". "
                "Det kan vara ilska, oro eller något barnet har sett. Prata lugnt med hen och ta det på allvar. Kontakta gärna skolan. "
                "Vid misstanke om att någon kan komma till skada: polisen 114 14, vid akut fara 112.")
    if niva == "oro":
        return (f"💛 {namn} verkar ha det tufft",
                f"{namn} skrev något {kalla} som tyder på att hen är ledsen eller har det jobbigt (till exempel ensamhet eller mobbning). "
                "Prata gärna med hen i lugn och ro. Skolans elevhälsa kan också hjälpa.")
    return None
