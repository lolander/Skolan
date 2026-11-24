"""Bygger webbdemon av lärarappen med en påhittad klass.  python larare/demo/bygg.py docs/demo

Allt körs i webbläsaren (shim.js svarar som lärarservern). Inget sparas och inget skickas.
"""
import json, sys, secrets, io, time, tempfile, shutil, datetime
from pathlib import Path
DEMO_TID = time.strftime("%Y-%m-%d %H:%M")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skolan_larare import server as s
s.lan_ip = lambda: "192.168.1.50"
ut = Path(sys.argv[1]); ut.mkdir(parents=True, exist_ok=True)
v = s.vecka_nu()
namn = ["Alva", "Bilal", "Clara", "Elias", "Freja", "Hugo", "Leo", "Maja", "Noah", "Saga", "Vera", "Omar"]
el = []
for i, n in enumerate(namn):
    f = {k: (i % 4 != 3) for k in s.FUNKTIONER}; f["mejl"] = i % 3 == 0
    e = {"id": f"e{i}", "lank": "x", "namn": n, "senast": f"2026-11-1{5 + i % 3} 1{i % 6}:2{i % 10}", "fel": "", "foralder": f,
         "veckobrev_nya": 0, "klass": {"vecka": v, "poang": 15 + i * 7} if f["klasslag"] else None}
    if i in (0, 2, 5, 9):
        e["rapport"] = {"fran": "2026-11-09", "till": "2026-11-15", "rader": [f"Övat {3 + i % 4} av 7 dagar", f"Glosförhör: {14 + i % 5}/20 rätt", "Läst kapitel 5 och 6", "Provplugg: Vikingatiden (2 pass)"]}
    if f["statistik"]:
        import random
        rnd = random.Random(i)
        mon = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
        pv = [{"vecka": "{}-W{:02d}".format(*(mon - datetime.timedelta(weeks=7 - w)).isocalendar()[:2]), "dagar": min(7, max(0, rnd.randint(1, 5) + (i % 3) - 1))} for w in range(8)]
        fh = [{"namn": n2, "datum": f"2026-11-{d:02d}", "n": 20, "ratt": rnd.randint(11, 20)} for n2, d in (("Engelska v.45", 6), ("Vikingar", 10), ("Engelska v.46", 13), ("Multiplikation", 16))]
        e["statistik"] = {"fran": pv[0]["vecka"], "till": "2026-11-17", "per_vecka": pv, "forhor": fh,
                          "prov": [{"namn": "Bråk", "amne": "Matte", "datum": "2026-11-07", "poang": rnd.randint(12, 25), "max": 25}],
                          "amnen": [{"namn": "Engelska", "dagar": rnd.randint(4, 12)}, {"namn": "SO", "dagar": rnd.randint(1, 6)}, {"namn": "Matte", "dagar": rnd.randint(1, 8)}]}
        e["mottagna"] = ["vb1", "mt1", "pr1-e%d-0" % i]
    if f["studieteknik"] and i in (0, 1, 4, 7):
        e["studieteknik"] = {"profil": ["Pluggar bäst direkt efter skolan, korta pass", "Läser hellre än skriver, vill ha musik på", "Gillar att bli förhörd av pappa", "Pluggar sent på kvällen"][i % 4],
            "ai_tankar": ["Övar ofta men bara på det hen redan kan. Mer tid på de svåra orden skulle ge mest.", "Börjar plugga kvällen innan prov. Pluggplanerna följs bättre när de har korta pass.",
                          "Bra på att göra förhören direkt. Skrivandet går framåt, särskilt stycken.", "Lägger in läxorna i tid men gör dem sent. Fokusläget hjälper."][i % 4],
            "svart": [["Bråk med olika nämnare", "Engelska oregelbundna verb"], ["Vikingatiden: årtal"], ["Multiplikation 7 och 8"], ["Stavning: dubbelteckning"]][i % 4],
            "svaga_punkter": [{"amne": "Matte", "antal": 3 + i % 3}, {"amne": "Engelska", "antal": 1 + i % 2}],
            "planer": [{"prov": "Vikingatiden", "amne": "SO", "datum": "2026-11-24", "sammanfattning": "4 korta pass: läsa kapitel 5–6, begrepp, årtal, övningsprov. 2 av 4 klara."}],
            "skrivande": {"tecken": 60 + i * 3, "stor": 75, "stycken": 40 + i * 5}, "riktlinjer": []}
    if f.get("lapp") and i in (0, 2, 5, 8):
        e["lappar"] = [{"id": f"l{i}", "tid": f"2026-11-1{4 + i % 4}T15:3{i}", "namn": n,
                        "text": ["Hej! Den här veckan har " + n + " tyckt att bråk med olika nämnare är svårt, särskilt att hitta gemensam nämnare. Orden 'although' och 'through' blev också fel flera gånger. Kanske något att ta upp igen?\n\nHälsningar",
                                 "Hej! " + n + " har övat mycket på veckans ord och det går bra. Det som var svårt var årtalen inför provet om vikingatiden.\n\nHälsningar",
                                 "Hej! Multiplikationstabellerna 7 och 8 har varit svåra för " + n + " den här veckan. Hen gör ofta fel på 7 × 8 och 8 × 6.\n\nHälsningar",
                                 "Hej! " + n + " tyckte att läsläxan var svår att förstå, särskilt orden 'besättning' och 'kölvatten'. Annars har det gått bra med glosorna.\n\nHälsningar"][(0, 2, 5, 8).index(i)]}]
    if f.get("samtal") and i in (0, 5):
        e["samtal"] = {"id": f"s{i}", "tid": "2026-11-17T20:10", "fran": "2026-09-22", "till": "2026-11-17", "per_vecka": 4.2,
            "amnen": {"Engelska": {"gjort": ["Övade glosorna \"Unit 4\" 12 gånger (84 % rätt direkt)", "Förhör \"Unit 4\": 17 av 20 rätt"], "svart": ["Ord som ofta blev fel i \"Unit 4\": although, through, enough"]},
                      "Matte": {"gjort": ["Prov \"Bråk\" 2026-11-07: pluggade 3 dagar, resultat 19 av 25"], "svart": ["Svag punkt: Bråk med olika nämnare"]},
                      "SO": {"gjort": ["Prov \"Vikingatiden\" 2026-11-24: pluggade 2 dagar", "Läsläxa \"Kapitel 5\" (klar)"], "svart": []}},
            "battre": ["Rätt direkt när du övar glosor: från 71 % till 86 %", "Snabbräkning (nivå): från 3 till 5"], "ovrigt": ["Skrivande: 6 övningar i Skrivverkstaden, 4 handskrivna texter", "Läshastighet: 112 ord per minut i snitt (5 mätningar)"],
            "ai": {"styrkor": ["Övar regelbundet, ungefär fyra dagar i veckan", "Glosorna har blivit mycket bättre sedan i höstas"], "svart": ["Bråk med olika nämnare", "Engelska ord med 'ough'"],
                   "fragor": ["Hur jobbar ni med bråk i klassrummet, så att vi kan göra likadant hemma?", "Hur fungerar hen i grupparbeten?"]}}
    el.append(e)
el[6]["fel"] = "Kunde inte nå elevens Läxspelet."
d = {"larar_id": "demo", "klass": "4B", "larare": "Anna Lärare", "inst": {k: True for k in s.FUNKTIONER} | {"mejl": False},
     "elever": el, "extra": {v: 40},
     "veckobrev": [{"id": "vb1", "titel": "Veckobrev v.47", "vecka": v, "skapad": "2026-11-16 15:10",
                    "ai": {"kapitel": 6, "kapitel_namn": "Skeppet", "las_dagar": [0, 2, 3], "ord": ["skepp", "segel", "hamn", "storm", "kompass", "ankare"],
                           "glosor": [["hund", "dog"], ["katt", "cat"]], "glosor_sprak": ["Svenska", "Engelska"]}}],
     "grupper": [
        {"id": "g1", "namn": "Grupp 1", "medlemmar": ["e0", "e3", "e7"], "uppgift": "Gör en affisch om vikingatiden", "datum": "2026-11-21", "skapad": "2026-11-16 09:05", "aktiv": True, "klara": {"e3": "2026-11-16 18:40"}},
        {"id": "g2", "namn": "Grupp 2", "medlemmar": ["e1", "e4", "e8"], "uppgift": "Gör en affisch om vikingatiden", "datum": "2026-11-21", "skapad": "2026-11-16 09:05", "aktiv": True, "klara": {}},
        {"id": "g0", "namn": "Bokcirkel", "medlemmar": ["e2", "e5", "e9", "e10"], "uppgift": "Läs Nils Holgersson kap 1–3", "datum": "2026-11-12", "skapad": "2026-11-05 10:00", "aktiv": False, "avslutad": "2026-11-12 14:00", "klara": {"e2": "x", "e9": "x"}}],
     "historik": [],
     "material": [{"id": "mt1", "typ": "material", "titel": "Sammanfattning vikingatiden", "amne": "SO", "text": "Läs inför provet", "datum": "", "max": None,
                   "fil": {"namn": "demo1.pdf", "mime": "application/pdf", "orig": "vikingar.pdf", "storlek": 120000}, "till": [], "resultat": {}, "skapad": "2026-11-15 14:00"},
                  {"id": "pr1", "typ": "prov", "titel": "Bråk", "amne": "Matte", "text": "", "datum": "2026-11-07", "max": 25.0, "fil": None, "till": [],
                   "resultat": {f"e{i}": {"poang": float(12 + (i * 5) % 14), "kommentar": "", "ver": 0} for i in range(0, 12, 2)}, "skapad": "2026-11-07 15:00"}]}
tmp = Path(tempfile.mkdtemp())
(tmp / "klass.json").write_text(json.dumps(d, ensure_ascii=False))
k = s.Klass(tmp, 8770)
for t, typ, txt in [("2026-11-05 10:00", "grupp", "Ny grupp Bokcirkel: Clara, Hugo, Saga, Vera. Uppgift: Läs Nils Holgersson kap 1–3"),
                    ("2026-11-12 14:00", "grupp", "Gruppen Bokcirkel avslutades. Klara: Clara, Saga. Anteckning: Bra diskussion!"),
                    ("2026-11-15 19:02", "rapport", "Rapport om Alva (2026-11-09 – 2026-11-15): Övat 3 av 7 dagar Glosförhör: 14/20 rätt"),
                    ("2026-11-16 09:05", "grupp", "Ny grupp Grupp 1: Alva, Elias, Maja. Uppgift: Gör en affisch om vikingatiden"),
                    ("2026-11-16 09:05", "grupp", "Ny grupp Grupp 2: Bilal, Freja, Noah. Uppgift: Gör en affisch om vikingatiden"),
                    ("2026-11-16 15:10", "veckobrev", "Veckobrev Veckobrev v.47 (v." + v + ")."),
                    ("2026-11-16 15:30", "anteckning", "Grupp 2 behöver lite mer tid med affischen."),
                    ("2026-11-16 18:40", "grupp", "Elias markerade gruppuppgiften i Grupp 1 som klar."),
                    ("2026-11-17 08:15", "synk", "Saga synkade."),
                    ("2026-11-17 20:12", "samtal", "Underlag till utvecklingssamtalet om Alva kom från föräldern."),
                    ("2026-11-17 15:35", "lapp", "Lapp från föräldern om Hugo: Multiplikationstabellerna 7 och 8 har varit svåra den här veckan.")]:
    k.d["historik"].append({"tid": t, "typ": typ, "text": txt})
# Påhittad skola: två kollegor, provkalender med en krock, ämneslärarnas resultat till mentorn (du)
idag = datetime.date.today()
dag = lambda n: (idag + datetime.timedelta(days=n)).isoformat()
k.d["roll"], k.d["amne"] = "mentor", "SO"
k.d["skola"] = {"id": "demo-skola", "namn": "Ekbackens skola", "hemlighet": "x", "kod": "EKBA-4B23", "kod_tid": time.time(),
    "medlemmar": {"LB": {"namn": "Bengt Engelska", "amne": "Engelska", "roll": "amne", "klass": "4B", "sedd": DEMO_TID, "adress": "10.0.4.18:8770"},
                  "LC": {"namn": "Cecilia Matte", "amne": "Matte, NO", "roll": "amne", "klass": "4B", "sedd": DEMO_TID, "adress": "10.0.4.22:8770"}},
    "prov": {"LB": [{"id": "pb1", "titel": "Glosprov Unit 5", "amne": "Engelska", "datum": dag(6), "klass": "4B"}],
             "LC": [{"id": "pc1", "titel": "Multiplikation", "amne": "Matte", "datum": dag(6), "klass": "4B"}, {"id": "pc2", "titel": "Växter", "amne": "NO", "datum": dag(13), "klass": "4B"}]},
    "resultat": {"LB": {"E0": [{"titel": "Glosprov Unit 4", "amne": "Engelska", "datum": dag(-12), "max": 20, "poang": 17, "kommentar": "Bra!", "larare": "Bengt Engelska"}],
                        "E2": [{"titel": "Glosprov Unit 4", "amne": "Engelska", "datum": dag(-12), "max": 20, "poang": 12, "kommentar": "", "larare": "Bengt Engelska"}]},
                 "LC": {"E0": [{"titel": "Bråk", "amne": "Matte", "datum": dag(-9), "max": 25, "poang": 21, "larare": "Cecilia Matte"}]}}}
k.d["material"].append({"id": "pa1", "typ": "prov", "titel": "Vikingatiden", "amne": "SO", "text": "", "datum": dag(7), "max": 30.0, "fil": None, "till": [], "resultat": {}, "skapad": "2026-11-16 10:00"})
k.d["skola"]["meddelanden"] = [
    {"id": "m1", "fran": "LC", "namn": "Cecilia Matte", "till": None, "text": "Hej! 4B har tre prov vecka 48. Kan någon flytta sitt prov en vecka?", "tid": DEMO_TID, "last": False},
    {"id": "m2", "fran": "LB", "namn": "Bengt Engelska", "till": k.d["larar_id"], "text": "Jag kan flytta glosprovet till v.49 om det passar dig.", "tid": DEMO_TID, "last": False}]
k.d["skola"]["anteckningar_in"] = {
    "LB": [{"id": "a1", "elev_id": "E0", "elev_namn": "Alva", "amne": "Engelska", "text": "Läser mycket bättre högt nu. Behöver öva på oregelbundna verb.", "larare": "Bengt Engelska", "tid": dag(-3)}],
    "LC": [{"id": "a2", "elev_id": "E0", "elev_namn": "Alva", "amne": "Matte", "text": "Har kommit ikapp med bråk. Textuppgifter är fortfarande svåra.", "larare": "Cecilia Matte", "tid": dag(-1)}]}
k.d["anteckningar"] = [{"id": "a0", "elev": "e0", "elev_id": "E0", "elev_namn": "Alva", "amne": "", "text": "Bra samtal med föräldrarna. Vi följer upp läsningen i januari.", "larare": "Anna Lärare", "tid": dag(-5)}]
for i, e in enumerate(k.d["elever"]):
    e["elev_id"] = f"E{i}"
    e["lararna"] = [{"id": k.d["larar_id"], "namn": "Anna Lärare", "amne": "SO", "roll": "mentor"},
                    {"id": "LB", "namn": "Bengt Engelska", "amne": "Engelska", "roll": "amne"}, {"id": "LC", "namn": "Cecilia Matte", "amne": "Matte, NO", "roll": "amne"}]
# Rektorsdelen: Anna är rektor, Bengt har nivå 2, Cecilia nivå 1, standard nivå 0
from skolan_larare import behorighet as beh
sk = k.d["skola"]
for lid in ("LB", "LC"):
    sk["medlemmar"][lid]["pub"] = beh.publik_nyckel(beh.ny_nyckel())
sk["policy"] = beh.ny_policy(sk["id"], k.d["larar_id"], "Anna Lärare", beh.publik_nyckel(k.d["nyckel"]), k.d["nyckel"])
sk["policy"]["beslut"][0]["tid"] = dag(-20) + " 08:30"
k.skola.satt_ratt(k.d["larar_id"], beh.niva_ratt(2), "Dataskyddsombudets bedömning 2026-11-02, dnr BUN 2026/412")
k.skola.satt_ratt("LB", beh.niva_ratt(2), "Dataskyddsombudets bedömning 2026-11-02, dnr BUN 2026/412")
k.skola.satt_ratt("LC", beh.niva_ratt(1), "Ämneslärare: bara namn och grupper behövs")
k.skola.satt_mentor(k.d["larar_id"], "4B", "Klassens mentor läsåret 2026/27")
k.skola.godkann("LB", "4B", "Engelska", None)
k.skola.godkann("LC", "4B", "Matte", None)
k.skola.satt_kontrollanter(["LB"], "Biträdande rektor enligt delegationsordningen")
k.d["skolkonto"] = {"token": "demo", "lev": "microsoft", "namn": "Anna Lärare", "epost": "anna.larare@ekbacken.se", "doman": "ekbacken.se", "org": "demo", "tid": int(time.time())}
for i, b_ in enumerate(sk["policy"]["beslut"][1:]):
    b_["tid"] = dag(-18 + i) + " 09:1" + str(i)
sk["policy"] = beh.signera_policy(sk["policy"], k.d["nyckel"])
k.d["inst"]["insikt"] = True
import random as _r
rnd = _r.Random(4)
ordlista = ["although", "through", "enough", "thought", "neighbour", "beautiful", "because", "friend"]
k.d["insikt"] = {v: {f"tok{i:02d}xyzab": {"ord": [[o, rnd.randint(1, 4)] for o in rnd.sample(ordlista, 4)], "ovat": i % 4 != 0,
                                           "prov": {"pa1": {"dagar": max(0, rnd.randint(-1, 4)), "plan": i % 3 == 0}}} for i in range(9)}}
L = k.publik(); shutil.rmtree(tmp)
import qrcode, qrcode.image.svg
buf = io.BytesIO(); qrcode.make(L["url"] + "/elev", image_factory=qrcode.image.svg.SvgPathImage).save(buf)
(ut / "qr.svg").write_bytes(buf.getvalue())
shutil.copy(s.WEBB / "ikon-64.png", ut / "ikon.png")
html = (s.WEBB / "index.html").read_text("utf-8").replace('"/ikon.png"', '"ikon.png"').replace('src="/api/qr.svg"', 'src="qr.svg"')
shim = (Path(__file__).parent / "shim.js").read_text("utf-8").replace("__LAGE__", json.dumps(L, ensure_ascii=False))
html = html.replace('<nav id="nav">', '<div class="demo">🧪 Demo med påhittad klass: du kan klicka runt, men inget sparas och inget skickas till eleverna.</div>\n<nav id="nav">')
html = html.replace("</style>", ".demo{background:#fff3cd;color:#664d03;padding:8px 20px;font-size:14px}</style>")
assert html.count("<script>\n") == 1, "lärarappen har fler skript än väntat"
html = html.replace("<script>\n", "<script>\n" + shim + "\n</script>\n<script>\n", 1)
html = html.replace('<a href="/api/beslut.csv">', '<a href="#behorighet" onclick="alert(\'I demon går det inte att ladda ner.\');return false">')
html = html.replace('<a href="/api/historik.csv">', '<a href="#historik" onclick="alert(\'I demon går det inte att ladda ner.\');return false">')
for a in ('<a href="/api/tillsyn_atkomst.csv">', '<a class="small" href="/api/tillsyn.json?begaran=${encodeURIComponent(b.id)}">'):
    assert a in html, a
    html = html.replace(a, '<a href="#skolan" onclick="alert(\'I demon går det inte att ladda ner.\');return false">')
(ut / "index.html").write_text(html, "utf-8")
print("ok", len(html))
