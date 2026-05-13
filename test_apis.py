"""
Script de test des APIs publiques de pharmacies françaises.
Exécuter avec : python3 test_apis.py
"""

import json
import requests

TIMEOUT = 15
DEPT = "42"


def print_separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def show_json_structure(data, max_depth=2, indent=0):
    """Affiche la structure récursive d'un JSON."""
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in list(data.items())[:8]:
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}: ({type(v).__name__})")
                if indent < max_depth:
                    show_json_structure(v, max_depth, indent + 1)
            else:
                val_str = str(v)[:80]
                print(f"{prefix}{k}: {val_str}")
    elif isinstance(data, list):
        print(f"{prefix}[liste de {len(data)} éléments]")
        if data and indent < max_depth:
            print(f"{prefix}  Premier élément :")
            show_json_structure(data[0], max_depth, indent + 1)


# ─── API 1 : Annuaire santé FHIR — type SA25 ─────────────────────────────────
print_separator("API 1 : Annuaire santé FHIR — type=SA25 (pharmacie d'officine)")
url1 = (
    f"https://api.annuaire.sante.fr/fhir/v1/Organization"
    f"?type=SA25&address-postalcode={DEPT}*&_count=10"
)
try:
    r1 = requests.get(url1, headers={"Accept": "application/fhir+json"}, timeout=TIMEOUT)
    print(f"Status : {r1.status_code}")
    data1 = r1.json()
    total = data1.get("total", "N/A")
    entries = data1.get("entry", [])
    print(f"total (bundle) : {total}")
    print(f"Nombre d'entrées dans cette page : {len(entries)}")
    print("\nStructure de la réponse :")
    show_json_structure(data1)
    if entries:
        print("\nPremière Organization (name + address) :")
        org = entries[0].get("resource", {})
        print(f"  name : {org.get('name')}")
        addr = org.get("address", [{}])[0]
        print(f"  address : {addr.get('line', [''])[0]}, {addr.get('postalCode')} {addr.get('city')}")
        ids = org.get("identifier", [])
        print(f"  identifiers : {[i.get('value') for i in ids[:3]]}")
except Exception as e:
    print(f"Erreur : {e}")

# ─── API 2 : Annuaire santé FHIR — type PHAR ─────────────────────────────────
print_separator("API 2 : Annuaire santé FHIR — type=PHAR")
url2 = (
    f"https://api.annuaire.sante.fr/fhir/v1/Organization"
    f"?type=PHAR&address-postalcode={DEPT}*&_count=10"
)
try:
    r2 = requests.get(url2, headers={"Accept": "application/fhir+json"}, timeout=TIMEOUT)
    print(f"Status : {r2.status_code}")
    data2 = r2.json()
    total2 = data2.get("total", "N/A")
    entries2 = data2.get("entry", [])
    print(f"total (bundle) : {total2}")
    print(f"Nombre d'entrées dans cette page : {len(entries2)}")
    print("\nStructure de la réponse :")
    show_json_structure(data2)
except Exception as e:
    print(f"Erreur : {e}")

# ─── API 3 : Overpass API (OpenStreetMap) ────────────────────────────────────
print_separator("API 3 : Overpass API (OpenStreetMap)")
url3 = "https://overpass-api.de/api/interpreter"
query3 = f'[out:json][timeout:30];(node[amenity=pharmacy]["addr:postcode"~"^{DEPT}"];);out 5;'
try:
    r3 = requests.post(url3, data={"data": query3}, timeout=60)
    print(f"Status : {r3.status_code}")
    data3 = r3.json()
    elements = data3.get("elements", [])
    print(f"Nombre d'éléments retournés (limité à 5) : {len(elements)}")
    print("\nStructure de la réponse :")
    show_json_structure(data3)
    if elements:
        print("\nPremier nœud :")
        el = elements[0]
        tags = el.get("tags", {})
        print(f"  id  : {el.get('id')}")
        print(f"  lat : {el.get('lat')}")
        print(f"  lon : {el.get('lon')}")
        print(f"  name : {tags.get('name')}")
        print(f"  addr:postcode : {tags.get('addr:postcode')}")
        print(f"  addr:city : {tags.get('addr:city')}")
        print(f"  phone : {tags.get('phone', tags.get('contact:phone'))}")
except Exception as e:
    print(f"Erreur : {e}")

# ─── API 4 : data.ameli.fr ────────────────────────────────────────────────────
print_separator("API 4 : data.ameli.fr — dataset pharmacies")
url4 = (
    "https://data.ameli.fr/api/explore/v2.1/catalog/datasets"
    f'/pharmacies/records?where=code_departement%3D%22{DEPT}%22&limit=5'
)
try:
    r4 = requests.get(url4, timeout=TIMEOUT)
    print(f"Status : {r4.status_code}")
    if r4.status_code == 200:
        data4 = r4.json()
        total4 = data4.get("total_count", data4.get("nhits", "N/A"))
        records = data4.get("results", data4.get("records", []))
        print(f"total_count : {total4}")
        print(f"Nombre de records retournés : {len(records)}")
        print("\nStructure de la réponse :")
        show_json_structure(data4)
    else:
        print(f"Contenu : {r4.text[:300]}")
except Exception as e:
    print(f"Erreur : {e}")

print("\n" + "="*60)
print("  FIN DES TESTS")
print("="*60)
