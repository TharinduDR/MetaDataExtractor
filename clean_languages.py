#!/usr/bin/env python3
"""
Post-processing script to clean up language fields in metadata JSON files.
Fixes: programming languages, ISO codes, duplicates, normalization,
       non-languages, typos, language families, modalities, language pairs,
       romanized variants, Arabic dialects, Italian dialects, writing systems,
       nationality/region labels, regional varieties of major languages,
       ALL-CAPS entries, underscore/hyphen variants, etc.

Usage:
    python cleanup_languages.py /path/to/json/files
    python cleanup_languages.py /path/to/json/files --dry-run --verbose
    python cleanup_languages.py /path/to/json/files --no-recursive  # top-level only
    python cleanup_languages.py combined.json --combined
    python cleanup_languages.py /path/to/json/files --outdir cleaned/
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

# =============================================================================
# 1. NORMALIZATION MAP: Map variant names to canonical form
# =============================================================================
NORMALIZE_MAP = {
    # =========================================================================
    # Chinese variants  (Mandarin and unspecified Chinese only → Chinese.
    # Cantonese, Min Nan, Hakka, Wu, etc. are KEPT SEPARATE since they have
    # their own ISO 639-3 codes (yue, nan, hak, wuu, ...).)
    # =========================================================================
    "Mandarin": "Chinese",
    "Mandarin Chinese": "Chinese",
    "Chinese (Mandarin)": "Chinese",
    "Chinese (Simplified)": "Chinese",
    "Simplified Chinese": "Chinese",
    "Chinese-simplified": "Chinese",
    "Chinese (Traditional)": "Chinese",
    "Traditional Chinese": "Chinese",
    "Chinese-traditional": "Chinese",
    "Classical Chinese": "Chinese",
    "cmn": "Chinese",
    "chn": "Chinese",
    "zh": "Chinese",
    "zho": "Chinese",

    # =========================================================================
    # Arabic variants & dialects → Arabic
    # =========================================================================
    "Modern Standard Arabic": "Arabic",
    "Moroccan Arabic": "Arabic",
    "Egyptian Arabic": "Arabic",
    "Tunisian Arabic": "Arabic",
    "Chadian Arabic": "Arabic",
    "Levantine Arabic": "Arabic",
    "Gulf Arabic": "Arabic",
    "Iraqi Arabic": "Arabic",
    "Maghrebi Arabic": "Arabic",
    "Levantine": "Arabic",
    "ar": "Arabic",
    "arq": "Arabic",
    "ary": "Arabic",

    # =========================================================================
    # German variants
    # =========================================================================
    "Standard German": "German",
    "Austrian German": "German",
    "Middle-High-German": "Middle High German",
    "de": "German",
    "deu": "German",
    "ger": "German",

    # =========================================================================
    # Portuguese variants
    # =========================================================================
    "Brazilian Portuguese": "Portuguese",
    "European Portuguese": "Portuguese",
    "Portuguese (African)": "Portuguese",
    "Brazilian": "Portuguese",
    "ptbr": "Portuguese",
    "ptmz": "Portuguese",
    "pt": "Portuguese",
    "por": "Portuguese",

    # =========================================================================
    # French variants
    # =========================================================================
    "French (African)": "French",
    "Canadian French": "French",
    "Hexagonal French": "French",
    "French (Quebec)": "French",
    # NOTE: "Middle French" → French has been REMOVED. Middle French (frm)
    # is a distinct historical language with its own ISO 639-3 code and is
    # preserved via REGIONAL_HISTORICAL_KEEPERS.
    "fr": "French",
    "fre": "French",

    # =========================================================================
    # Spanish variants
    # =========================================================================
    "Argentine Spanish": "Spanish",
    "Peninsular Spanish": "Spanish",
    "Mexican Spanish": "Spanish",
    "Caribbean Spanish": "Spanish",
    "European Spanish": "Spanish",
    "Latin American Spanish": "Spanish",
    "es": "Spanish",
    "esp": "Spanish",
    "spa": "Spanish",

    # =========================================================================
    # Persian variants
    # =========================================================================
    "Farsi": "Persian",
    "Western Persian": "Persian",
    "Dari": "Persian",
    "Tajik Persian": "Persian",

    # =========================================================================
    # Hindi variants
    # =========================================================================
    "hi": "Hindi",
    "hin": "Hindi",

    # =========================================================================
    # Italian variants
    # =========================================================================
    "it": "Italian",
    "ita": "Italian",

    # =========================================================================
    # Russian ISO codes
    # =========================================================================
    "ru": "Russian",
    "rus": "Russian",

    # =========================================================================
    # Dutch variants
    # =========================================================================
    "Flemish": "Dutch",
    "West Flemish": "Dutch",
    "dut": "Dutch",
    "nld": "Dutch",

    # =========================================================================
    # Romanian variants
    # =========================================================================
    "Moldavian": "Romanian",
    "ron": "Romanian",

    # =========================================================================
    # Bengali variants
    # =========================================================================
    "Bangla": "Bengali",
    "Bengla": "Bengali",
    "Bengali Romanized": "Bengali",
    "West Bengali": "Bengali",
    "ben": "Bengali",
    "bn": "Bengali",

    # =========================================================================
    # Telugu variants
    # =========================================================================
    "Telugu Romanized": "Telugu",
    "tel": "Telugu",

    # =========================================================================
    # Punjabi variants
    # =========================================================================
    "Panjabi": "Punjabi",
    "Eastern Panjabi": "Punjabi",

    # =========================================================================
    # Uyghur variants
    # =========================================================================
    "Uighur": "Uyghur",

    # =========================================================================
    # Zulu variants
    # =========================================================================
    "isiZulu": "Zulu",
    "zul": "Zulu",

    # =========================================================================
    # Xhosa variants
    # =========================================================================
    "isiXhosa": "Xhosa",
    "xho": "Xhosa",

    # =========================================================================
    # Indonesian variants
    # =========================================================================
    "Bahasa Indonesian": "Indonesian",
    "ind": "Indonesian",

    # =========================================================================
    # Sesotho / Sotho variants (Southern Sotho)
    # =========================================================================
    "Sotho": "Sesotho",
    "Southern Sotho": "Sesotho",

    # =========================================================================
    # Northern Sotho / Sepedi variants
    # =========================================================================
    "Sesotho sa Leboa": "Northern Sotho",
    "Sesotho sa Lebowa": "Northern Sotho",
    "Sepedi": "Northern Sotho",
    "N. Sotho": "Northern Sotho",
    "S. Sotho": "Sesotho",

    # =========================================================================
    # Other South African Bantu-prefix collapses
    # =========================================================================
    "isiNdebele": "Ndebele",
    "SiSwati": "Swazi",
    "Swati": "Swazi",
    "Tshivenda": "Venda",
    "Xitsonga": "Tsonga",

    # =========================================================================
    # English variants (regional varieties collapse to English)
    # =========================================================================
    "Standard English": "English",
    "American English": "English",
    "American": "English",
    "British English": "English",
    "British": "English",
    "Gen. American English": "English",
    "General American English": "English",
    "M. English": "English",
    "eng": "English",
    "en": "English",

    # =========================================================================
    # Hebrew variants
    # =========================================================================
    "Modern Hebrew": "Hebrew",
    "heb": "Hebrew",

    # =========================================================================
    # Azerbaijani variants (also "Azerbaijani Turkish" → Azerbaijani)
    # =========================================================================
    "North Azerbaijani": "Azerbaijani",
    "Azeri": "Azerbaijani",
    "Azerbaijani Turkish": "Azerbaijani",

    # =========================================================================
    # Armenian variants
    # =========================================================================
    "Western Armenian": "Armenian",

    # =========================================================================
    # Burmese variants
    # =========================================================================
    "Myanmar": "Burmese",

    # =========================================================================
    # Lao variants
    # =========================================================================
    "Laos": "Lao",

    # =========================================================================
    # Pashto variants
    # =========================================================================
    "Southern Pashto": "Pashto",
    "Pushto": "Pashto",

    # =========================================================================
    # Shona variants
    # =========================================================================
    "ChiShona": "Shona",

    # =========================================================================
    # Swahili variants
    # =========================================================================
    "Kiswahili": "Swahili",
    "SwaHili": "Swahili",
    "swa": "Swahili",

    # =========================================================================
    # Luganda variants
    # =========================================================================
    "Ganda": "Luganda",

    # =========================================================================
    # Setswana variants
    # =========================================================================
    "Tswana": "Setswana",

    # =========================================================================
    # Chichewa / Nyanja variants
    # =========================================================================
    "Chewa": "Chichewa",
    "Nyanja": "Chichewa",

    # =========================================================================
    # Latvian variants
    # =========================================================================
    "Standard Latvian": "Latvian",

    # =========================================================================
    # Malay variants
    # =========================================================================
    "Standard Malay": "Malay",

    # =========================================================================
    # Norwegian variants
    # =========================================================================
    "Norwegian Bokmål": "Norwegian",
    "Norwegian Nynorsk": "Norwegian",
    "Norwegian (Bokmål)": "Norwegian",
    "Norwegian (Nynorsk)": "Norwegian",
    "Bokmål": "Norwegian",
    "Bokmal": "Norwegian",
    "Nynorsk": "Norwegian",

    # =========================================================================
    # Malagasy variants
    # =========================================================================
    "Plateau Malagasy": "Malagasy",

    # =========================================================================
    # Uzbek variants
    # =========================================================================
    "Northern Uzbek": "Uzbek",

    # =========================================================================
    # Bambara variants
    # =========================================================================
    "Bamanankan": "Bambara",

    # =========================================================================
    # Nigerian Pidgin variants (Naija = colloquial name for Nigerian Pidgin)
    # =========================================================================
    "Nigerian-Pidgin": "Nigerian Pidgin",
    "Naija": "Nigerian Pidgin",

    # =========================================================================
    # Slovenian variants
    # =========================================================================
    "Slovene": "Slovenian",

    # =========================================================================
    # Sinhala variants
    # =========================================================================
    "Sinhalese": "Sinhala",

    # =========================================================================
    # Greek variants
    # =========================================================================
    "Modern Greek": "Greek",

    # =========================================================================
    # Ilocano variants
    # =========================================================================
    "Ilokano": "Ilocano",

    # =========================================================================
    # Urdu variants
    # =========================================================================
    "Roman Urdu": "Urdu",

    # =========================================================================
    # Quechua variants
    # =========================================================================
    "Eastern Apurímac Quechua": "Quechua",
    "Cusco Quechua": "Quechua",

    # =========================================================================
    # Mongolian variants
    # =========================================================================
    "Halh Mongolian": "Mongolian",
    "Khalkha": "Mongolian",

    # =========================================================================
    # Navajo variants
    # =========================================================================
    "Navaho": "Navajo",

    # =========================================================================
    # Odia variants
    # =========================================================================
    "Oriya": "Odia",
    "Odiya": "Odia",

    # =========================================================================
    # Oromo variants
    # =========================================================================
    "Oromo (West Central)": "Oromo",
    "Afaan Oromo": "Oromo",

    # =========================================================================
    # Haitian Creole variants
    # =========================================================================
    "Haitian": "Haitian Creole",

    # =========================================================================
    # Maori variants (diacritic normalization)
    # =========================================================================
    "Māori": "Maori",
    "C.I. Māori": "Cook Islands Maori",
    "Cook Islands Māori": "Cook Islands Maori",

    # =========================================================================
    # Sami variants — collapse ALL to "Northern Sami" except dialects with
    # their own ISO codes (Skolt Sami, Pite Sami, Kildin Saami → kept;
    # standardise casing)
    # NOTE: Generic "Sami"/"Saami"/"North Sami"/"North Saami"/"North_Sami"
    #       → Northern Sami
    # =========================================================================
    "Sámi": "Northern Sami",
    "Sami": "Northern Sami",
    "Saami": "Northern Sami",
    "North Sami": "Northern Sami",
    "North Saami": "Northern Sami",
    "North Sámi": "Northern Sami",
    "North_Sami": "Northern Sami",
    "Northern Sámi": "Northern Sami",
    "Northern Saami": "Northern Sami",
    "Pite Saami": "Pite Sami",
    "Kildin Saami": "Kildin Sami",
    # Skolt Sami stays as-is (distinct ISO code: sms)

    # =========================================================================
    # Sorbian variants (canonical: "Upper Sorbian", "Lower Sorbian")
    # =========================================================================
    "Sorbian (Upper)": "Upper Sorbian",
    "Upper_Sorbian": "Upper Sorbian",
    "Sorbian Upper": "Upper Sorbian",

    # =========================================================================
    # Old Church Slavonic variants
    # =========================================================================
    "Old-Church-Slavonic": "Old Church Slavonic",
    "Old_Church_Slavonic": "Old Church Slavonic",
    "Old Slavic": "Old Church Slavonic",

    # =========================================================================
    # Cree variants — collapse "Plain Cree" typo, keep dialects distinct
    # (Plains Cree, East Cree have separate ISO codes; bare "Cree" → Cree)
    # =========================================================================
    "Plain Cree": "Plains Cree",

    # =========================================================================
    # Shipibo-Konibo casing
    # =========================================================================
    "Shipibo-konibo": "Shipibo-Konibo",

    # =========================================================================
    # Manipuri variants
    # =========================================================================
    "Meitei": "Manipuri",

    # =========================================================================
    # Frisian variants
    # =========================================================================
    "West Frisian": "Frisian",

    # =========================================================================
    # Fulfulde / Fula variants
    # =========================================================================
    "Fulfulde (Nigerian)": "Fulfulde",

    # =========================================================================
    # Kurdish variants
    # =========================================================================
    "Kurmanji Kurdish": "Kurdish",
    "Sorani Kurdish": "Kurdish",
    "Kurmanji": "Kurdish",
    "Sorani": "Kurdish",

    # =========================================================================
    # Italian dialect labels → standalone dialect names
    # =========================================================================
    "Italian (Sicilian)": "Sicilian",
    "Italian (Neapolitan)": "Neapolitan",
    "Italian (Tuscan)": "Tuscan",
    "Italian (Venetian)": "Venetian",
    "Italian (Emilian)": "Emilian",
    "Italian (Lombard)": "Lombard",
    "Italian (Friulian)": "Friulian",
    "Italian (Sardinian)": "Sardinian",

    # =========================================================================
    # Diacritic / accent variants
    # =========================================================================
    "Yorùbá": "Yoruba",
    "Éwé": "Ewe",
    "Gà": "Ga",
    "Asháninka": "Ashaninka",
    "Bâsâa": "Basaa",
    "Paraguayan Guaraní": "Guarani",
    "Murrinh-patha": "Murrinhpatha",

    # =========================================================================
    # Sakha / Yakut variants (Sakha is the modern preferred name)
    # =========================================================================
    "Sakha (Yakut)": "Sakha",
    "Yakut": "Sakha",
    "YAKUT": "Sakha",

    # =========================================================================
    # ALL-CAPS variants → proper case
    # =========================================================================
    "LOKAA": "Lokaa",
    "KIKONGO": "Kongo",
    "Kikongo": "Kongo",
    "Koongo": "Kongo",
    "IMDLAWN TASHLHIYT": "Tashelhiyt",
    "Imdlawn Tashlhiyt": "Tashelhiyt",
    "Berber": "Tashelhiyt",  # ambiguous family name → most common variant

    # =========================================================================
    # Typos
    # =========================================================================
    "Malayam": "Malayalam",
    "Urdi": "Urdu",
    "Galacian": "Galician",
    "Glacian": "Galician",
    "Komi-Ziran": "Komi-Zyrian",
    "Alsacian": "Alsatian",
    "Kinyabwana": "Kinyarwanda",

    # =========================================================================
    # Tigrinya variants
    # =========================================================================
    "Tigrigna": "Tigrinya",

    # =========================================================================
    # Irish variants (Irish Gaelic is the same language as Irish, ISO: gle)
    # =========================================================================
    "Irish Gaelic": "Irish",

    # =========================================================================
    # Scottish — ambiguous bare term, resolved to Scottish Gaelic per
    # user instruction (ISO: gla)
    # =========================================================================
    "Scottish": "Scottish Gaelic",
    "Scots Gaelic": "Scottish Gaelic",

    # =========================================================================
    # Ethiopic — interpreted as Ge'ez the language (ISO: gez), NOT the script
    # =========================================================================
    "Ethiopic": "Ge'ez",

    # =========================================================================
    # Additional typos / diacritic variants / native-name synonyms
    # =========================================================================
    "Pastho": "Pashto",            # typo
    "Toki Pisin": "Tok Pisin",     # typo
    "Columbian Spanish": "Spanish",  # typo + regional collapse to parent
    "Guaraní": "Guarani",          # diacritic
    "Euskara": "Basque",           # native name
    "Bhutanese": "Dzongkha",       # nationality → language
    "Nepalese": "Nepali",          # nationality → language
    "Lezgi": "Lezgian",            # spelling variant
    "Myanmar (Burmese)": "Burmese",  # parenthetical clarification
    "Syriac": "Classical Syriac",  # most NLP corpora mean syc, not syr
    "Central Khmer": "Khmer",      # = Khmer macrolanguage
    "Chaldean": "Chaldean Neo-Aramaic",  # cld — the language, not the church
    "Dholuo": "Luo",               # Dholuo is the native name for Luo (luo)

    # Spelling / diacritic variants and synonyms (added this round)
    "Faroeese": "Faroese",                 # typo
    "Kirghiz": "Kyrgyz",                   # spelling variant
    "Divehi": "Dhivehi",                   # spelling variant
    "Iloko": "Ilocano",                    # native name (Iloko = Ilocano)
    "South Saami": "South Sami",           # Saami → Sami consistency
    "Hakka Chinese": "Hakka",              # = Hakka
    "Church Slavic": "Old Church Slavonic",  # synonym
    "Nzébi": "Nzebi",                      # diacritic → bare form for merging
    "Low-saxon": "Low Saxon",              # hyphen → space
    "Waray-waray": "Waray",                # reduplicated native name
    "Komi Permyak": "Komi-Permyak",        # consistency with Komi-Zyrian
    # NOTE: bare "Mari" (without a regional qualifier) is ambiguous; per user
    # decision, collapse to the most common variety "Meadow Mari". The
    # specific entries "Eastern Mari", "Western Mari", "Hill Mari", and
    # "Meadow Mari" are preserved as-is.
    "Mari": "Meadow Mari",

    # Hyphenated-lowercase variants (added this round)
    "Norwegian-bokmål": "Norwegian",       # existing Norwegian-collapse policy
    "Norwegian-nynorsk": "Norwegian",
    "South-azerbaijani": "Azerbaijani",    # existing Azerbaijani-collapse policy
    "Western-punjabi": "Western Panjabi",  # hyphen → space (keep distinct from Punjabi: ISO pnb)

    # Algerian Arabic → Arabic (per existing Arabic dialect policy)
    "Algerian": "Arabic",                  # nationality label = Algerian Arabic
    "Algerian Arabic": "Arabic",

    # =========================================================================
    # Year-5 additions: typos, diacritic merges, native names, synonyms
    # =========================================================================
    # Apostrophe fixes
    "Mikmaq": "Mi'kmaq",
    "Tsuet'ina": "Tsuut'ina",
    # Hindi-belt typos
    "Garwali": "Garhwali",
    "Chattisgarhi": "Chhattisgarhi",
    "Brajbhasha": "Braj Bhasha",
    # Diacritic strips for indigenous-language names (consistent with
    # existing canonical forms: Nahuatl, Guarani, Ashaninka)
    "Náhuatl": "Nahuatl",
    "Mundurukú": "Munduruku",
    "Rarámuri": "Raramuri",
    "Simba Guaraní": "Simba Guarani",
    "Mbya Guaraní": "Mbya Guarani",
    # Ghomala variants
    "Ghomdá": "Ghomala",
    # Sami / Saami consistency
    "Saami South": "South Sami",
    "Skolt": "Skolt Sami",        # bare term → canonical
    # Native names → English canonical
    "nêhiyawêwin": "Plains Cree",
    "Morisien": "Mauritian Creole",
    "Gwadeloupéyen": "Guadeloupean Creole",
    "Bahasa Melayu": "Malay",
    # Synonyms / merger normalizations
    "Achinese": "Acehnese",
    "Banjar": "Banjarese",
    "Faroe": "Faroese",
    "Wixarica": "Wixarika",
    "Western Frisian": "Frisian",
    "Shipibo": "Shipibo-Konibo",
    "Gunwinggu": "Kunwinjku",
    "Kunwok": "Kunwinjku",
    "Inuptiaq": "Inupiaq",
    "Inupiatum": "Inupiaq",
    # Strip script annotation
    "Chinese Simplified": "Chinese",
    # User-decided ambiguities
    "Gaelic": "Scottish Gaelic",
    "Yucatec Maya": "Yucatec",
    "Akan/Twi": "Akan",
    "Inuktut": "Inuktitut",
    "Old Awadhi": "Awadhi",
    # Chewa; Nyanja → both are nya, same as Chichewa
    "Chewa; Nyanja": "Chichewa",
    # Visayan family resolution (per existing Bisaya → Cebuano rule)
    "Visayan": "Cebuano",
    # Runyankole / Runyankore spelling variant
    "Runyankole": "Runyankore",

    # =========================================================================
    # Year-6 additions: typos, diacritic merges, native names, synonyms
    # =========================================================================
    # Typos
    "Telegu": "Telugu",
    "Irisht": "Irish",
    "Najja": "Nigerian Pidgin",        # typo of Naija
    "Tsilhq'ut'in": "Tsilhqot'in",     # typo (extra apostrophe)
    "Vorú": "Võro",                    # typo
    # Abbreviated forms → full names
    "Imb. Quechua": "Imbabura Quechua",
    "Zin. Tzotzil": "Zinacantán Tzotzil",
    "Swiss G.": "Swiss German",
    # Native names / synonyms
    "Gagana": "Samoan",                # Gagana Sāmoa is the native name
    "Bahasa Indonesia": "Indonesian",
    "Persian Farsi": "Persian",        # redundant tautology
    "Dari Persian": "Persian",         # = Persian variety (per Persian-collapse policy)
    "Azeri Turkish": "Azerbaijani",
    "Iranian Azerbaijani": "Azerbaijani",
    "Sibe": "Xibe",                    # alt spelling (ISO sjo)
    "Myanmar Written Language": "Burmese",
    "Bokmål (Norwegian)": "Norwegian",
    "Biblical Hebrew": "Hebrew",
    "Assyrian": "Assyrian Neo-Aramaic",
    # Arabic dialect collapse (existing policy)
    "Sudanese Arabic": "Arabic",
    "Darija": "Arabic",                # Moroccan Arabic colloquial name
    "Moroccan Arabic/Darija": "Arabic",
    # Mozambican Portuguese collapse (existing policy on regional Portuguese)
    "Mozambican Portuguese": "Portuguese",
    "Mozambique Portuguese": "Portuguese",
    # Diacritic strips
    "Èdò": "Edo",
    "Ghomálá'": "Ghomala",
    # Sami diacritic strips (consistency with existing Northern Sami etc.)
    "Inari Sámi": "Inari Sami",
    "Lule Sámi": "Lule Sami",
    "South Sámi": "South Sami",
    "Pite Sámi": "Pite Sami",
    "Skolt Sámi": "Skolt Sami",
    # Serbian script-annotation strip
    "Serbian (Cyrillic)": "Serbian",
    "Serbian (Latin)": "Serbian",
    "Serbian Cyrillic": "Serbian",
    "Serbian Latin": "Serbian",
    # Livvi Karelian = Livvi (same language, ISO olo)
    "Livvi Karelian": "Livvi",

    # =========================================================================
    # Year-7 additions
    # =========================================================================
    # ---- Typos ----
    "Tajiki": "Tajik",
    "Slovakian": "Slovak",
    "Urd": "Urdu",
    "Gitskan": "Gitksan",
    "Banjarase": "Banjarese",
    "Africans": "Afrikaans",
    "N. Pidgin": "Nigerian Pidgin",
    "Moore": "Mossi",          # the language: Mooré / Mòoré
    "Komi Ziryan": "Komi-Zyrian",

    # ---- Diacritic merges (consistent with existing strip-policy for
    #      indigenous-language names where a no-diacritic canonical exists) ----
    "Apurinã": "Apurina",
    "Tupinambá": "Tupinamba",
    "Yoloxóchitl Mixtec": "Yoloxochitl Mixtec",
    # Note: Cabécar (cjp), Apinayé (apn), Wichí (mzh), Mündü (muh) all keep
    # their diacritics — no no-diacritic variant has appeared in the data,
    # so stripping serves no merge purpose.

    # ---- Native names → English canonical ----
    "Shqip": "Albanian",                       # Shqip = Albanian
    "Afaan Oromoo": "Oromo",                   # native name
    "Tarahumara": "Raramuri",                  # Spanish name → native canonical
    "Kréyol": "Haitian Creole",                # generic Kréyol most often = Haitian
    "Kréyòl Gwadeloupéyen": "Guadeloupean Creole",

    # ---- Synonyms / merges ----
    "Nyankore": "Runyankore",
    "Bikolano": "Bikol",
    "Halh": "Mongolian",
    "Khalkha Mongolian": "Mongolian",
    "Russia Buriat": "Buryat",
    "North Macedonian": "Macedonian",          # country-adjective form
    "Batak Toba": "Toba Batak",                # word-order swap
    "Quiché": "K'iche'",
    "k'iche'": "K'iche'",                      # lowercase casing fix
    "Sereer": "Seereer",                       # spelling unification
    # Bare Chinese province names (Sichuan, Yunnan, Hubei, Henan) are
    # excluded as ambiguous regional labels — see EXCLUDE_SET below.
    "Chol": "Ch'ol",                           # add apostrophe (= ctu)
    "Yucatec Mayan": "Yucatec",                # synonym
    "Yukatek Maya": "Yucatec",                 # synonym
    "Apurina": "Apurina",                      # canonical (no-op, listed for clarity)

    # ---- Hindi-belt regional varieties without ISO 639-3 codes ----
    # (Bundeli, Kannauji, Khadi Boli, Malwi, Bhadavari, Himachali, Pichwara,
    #  Pahari, Bhotiya, etc. — kept as-is when they have ISO codes; below
    #  variants that don't are normalized.)

    # ---- Strip script/diacritic annotations from regional-variant labels ----
    "Hebrew, Unvocalized": "Hebrew",
    "Arabic, Egyptian": "Arabic",
    "Hñähñu": "Otomi",                         # Hñähñu is native name for Otomi
    "Hñähñu/Otomí": "Otomi",
    "Otomí": "Otomi",

    # ---- Guaraní varieties (with diacritics) — collapse to no-diacritic
    #      varieties where existing canonical exists. Distinct ISO codes are
    #      preserved as separate languages. ----
    "Guarani Mbya": "Mbya Guarani",            # word-order normalization
    "Guaraní Mbya": "Mbya Guarani",
    "Guaraní Paraguayan": "Paraguayan Guarani",
    "Guaraní Eastern Bolivian": "Eastern Bolivian Guarani",
    "Guaraní Western Bolivian": "Western Bolivian Guarani",
    "Paraguayan Guarani": "Paraguayan Guarani",  # canonical

    # ---- Compound semicolon/comma/slash labels → canonical single language ----
    # (Per user decision: collapse split-style labels.)
    "Dutch; Flemish": "Dutch",
    "Pushto; Pashto": "Pashto",
    "Romanian; Moldavian; Moldovan": "Romanian",
    "Moldovan": "Romanian",
    "Naija/Nigerian Pidgin": "Nigerian Pidgin",
    "Aranese/Occitan": "Occitan",
    # ↑ Aranese was previously kept distinct, but the compound label asks to
    # collapse. Aranese alone is preserved (it has data of its own).

    # ---- Parenthetical-variety labels (collapse to parent) ----
    "Greenlandic (South)": "Greenlandic",
    "Romani (Lovari)": "Romani",
    "Tat (Muslim)": "Tat",
    "Shehri (Jibbali)": "Shehri",
    "Yukaghir (Kolyma)": "Kolyma Yukaghir",    # Kolyma Yukaghir has own ISO yux
    "Meitei (Manipuri)": "Manipuri",           # Meitei = Manipuri

    # ---- Eastern Armenian → Armenian (existing rule already covers
    #      Western Armenian; do same for Eastern) ----
    "Eastern Armenian": "Armenian",

    # ---- Year-7 Arabic dialect collapses (existing Arabic dialect policy) ----
    "Algerian Dialect": "Arabic",
    "North Levantine Arabic": "Arabic",

    # ---- Kurdish variety collapses (existing Kurdish-collapse policy) ----
    "Central Kurdish": "Kurdish",
    "Northern Kurdish": "Kurdish",

    # ---- Quechua variety collapses where no separate ISO code ----
    # Eastern Apurimac Quechua has ISO qve — kept distinct; leave unchanged
    # Central Aymara has ISO ayc — kept distinct; leave unchanged
    # Western Sierra Puebla Nahuatl — distinct Nahuatl variety, has own ISO

    # ---- Yazva (= Yazva Komi, a dialect of Komi-Permyak) ----
    "Yazva": "Komi-Permyak",

    # ---- Earlier Egyptian = Ancient Egyptian variety ----
    "Earlier Egyptian": "Ancient Egyptian",
    "Egyptian": "Arabic",      # bare "Egyptian" → Egyptian Arabic per Arabic policy
    # Note: if you mean Ancient Egyptian, use the explicit form.

    # ---- Classical & Late Latin → match existing "Classical and Late Latin" ----
    "Classical & Late Latin": "Classical and Late Latin",

    # ---- Sami diacritic strips (already covered for prior years; add bare
    #      forms here too) ----
    "Sámi": "Northern Sami",

    # ---- Wu Chinese / Yue Chinese / Taiwanese Hakka / Taiwanese Hokkien
    #      — keep separate since each has its own ISO 639-3 code (wuu / yue /
    #      hak / nan). No mapping. ----

    # ---- Classical Armenian → already in EXCLUDE? no — has ISO xcl,
    #      same as Old Armenian. Map both to one canonical form. ----
    "Classical Armenian": "Old Armenian",

    # ---- Old High German has ISO goh — keep as-is. ----

    # ---- Dagur (mongolic, dta), Bajau (multiple ISO codes), Naxi (nxq/nbf),
    #      Hokkien (= Min Nan, but Hokkien has own ISO hbl?) — actually Hokkien
    #      = Min Nan; both have separate widely-used labels. Keep both. ----

    # =========================================================================
    # Year-8 additions
    # =========================================================================
    # ---- Typos ----
    "Azerbajani": "Azerbaijani",
    "Santhali": "Santali",
    "Finish": "Finnish",
    "Asamese": "Assamese",
    "EfiK": "Efik",                          # casing
    "Lezghian": "Lezgian",
    "Bhilli": "Bhili",
    "Kiche": "K'iche'",
    "Tsuum'ina": "Tsuut'ina",
    "Arápa ho": "Arapaho",                   # data-error space split
    "SeSotho": "Sesotho",                    # camelcase normalisation
    "Senćofen": "Senćoten",                  # typo (f → t)

    # ---- Diacritic merges ----
    "Mapudungún": "Mapudungun",

    # ---- Native names / synonyms → English canonical ----
    "Afan Oromo": "Oromo",
    "Quechuan": "Quechua",
    "Jinghpaw": "Jingpho",
    "Aceh": "Acehnese",
    "Bali": "Balinese",
    "Bhutani": "Dzongkha",
    "Niue": "Niuean",
    "Samoa": "Samoan",
    "Tokelau": "Tokelauan",
    "Sylhet": "Sylheti",
    "Chittagong": "Chittagonian",
    "Rromani": "Romani",
    "te reo Māori": "Maori",
    "Yup'ik": "Yupik",
    "Ossetic": "Ossetian",
    "Naija Pidgin": "Nigerian Pidgin",
    "Modern Turkish": "Turkish",
    "Tetum": "Tetun",
    "Standard Arabic": "Arabic",
    "Sāotomense": "São Tomense",
    "Newari": "Newar",
    "Church Slavonic": "Old Church Slavonic",
    "Fulah": "Fula",

    # ---- Bhutia/Sikkimese (= sip) ----
    "Bhutia": "Sikkimese",

    # ---- North/South Ndebele canonical names ----
    "North Ndebele": "Northern Ndebele",
    "South Ndebele": "Southern Ndebele",

    # ---- Sichuan Yi → Yi ----
    "Sichuan Yi": "Yi",

    # ---- Twi variants (per user policy: all → Twi) ----
    "Asante Twi": "Twi",
    "Asante-twi": "Twi",
    "Akuapim-twi": "Twi",

    # ---- Bavarian German → Bavarian ----
    "Bavarian German": "Bavarian",

    # ---- Walliserdeutsch → Swiss German ----
    "Walliserdeutsch": "Swiss German",

    # ---- Kiribati / I-Kiribati / Gilbertese (all = gil) ----
    "I-Kiribati": "Kiribati",
    "Gilbertese": "Kiribati",

    # ---- Seereer spelling unification ----
    "Serer": "Seereer",

    # ---- Caribbean/island nationality labels → French-based creoles ----
    "Mauritian": "Mauritian Creole",
    "Martinican": "Martinican Creole",
    "Guadeloupean": "Guadeloupean Creole",
    "Seychellois": "Seychellois Creole",
    "Antillean": "Antillean Creole",
    "Saint Lucian Patois": "Saint Lucian Creole",

    # ---- Arabic dialect collapses (per existing Arabic policy) ----
    "Arabic (Algerian)": "Arabic",
    "Arabic (Moroccan)": "Arabic",
    "Moroccan Darija": "Arabic",
    "South Levantine Arabic": "Arabic",
    "Najdi Arabic": "Arabic",
    "Standard Moroccan Tamazight": "Tamazight",

    # ---- Compound Chinese-variety labels ----
    "Chinese (Min Nan)": "Min Nan",
    "Mandarin (Taiwan)": "Chinese",
    "Min Dong Chinese": "Min Dong",

    # ---- Parenthetical-variety labels (collapse to parent) ----
    "Tonga (Zambia)": "Tonga",
    "Luo (Kenya and Tanzania)": "Luo",

    # ---- camelCase concatenated labels → parent ----
    "PortugueseBr": "Portuguese",
    "PortuguesePt": "Portuguese",

    # ---- Abbreviated forms ----
    "N. Azerbaijani": "Azerbaijani",
    "N. Uzbek": "Uzbek",
    "South Azerbaijani": "Azerbaijani",
    "Southern Uzbek": "Uzbek",

    # ---- Iranian/Kurdish variety collapses (existing policies) ----
    "Northern Luri": "Persian",
    "Mazanderani": "Mazandarani",
    "Southern Kurdish": "Kurdish",
    "Laki Kurdish": "Kurdish",

    # ---- Korean variety spelling ----
    "Jeju-eo": "Jejueo",

    # ---- SLI Yupik abbreviation → St Lawrence Yupik (existing year-7 entry) ----
    "SLI Yupik": "St Lawrence Yupik",

    # Crimean Turkish → Crimean Tatar (user decision: merge)
    "Crimean Turkish": "Crimean Tatar",

    # Russian (Latin), Chinese (Latin) — strip script annotation
    "Russian (Latin)": "Russian",
    "Chinese (Latin)": "Chinese",

    # Cypriot Greek → Greek (regional variety, no separate ISO code at 639-3)
    "Cypriot Greek": "Greek",

    # Bisaya → Cebuano (Bisaya is the umbrella native term; in practice
    # most NLP corpora labelled "Bisaya" refer to Cebuano)
    "Bisaya": "Cebuano",

    # ALL camelcase variants (run-together words) → spaced canonical form
    "WelshRomani": "Welsh Romani",
    "VlaxRomani": "Vlax Romani",
    "WesternPanjabi": "Western Panjabi",     # has own ISO code pnb, keep distinct
    "SoutheastPashayi": "Southeast Pashayi",
    "NortheastPashayi": "Northeast Pashayi",
    "NorthwestPashayi": "Northwest Pashayi",
    "MahasuPahari": "Mahasu Pahari",
    # NOTE: "MiiPro" is a corpus tag (the MiiPro Japanese child-language
    # corpus), not a language — handled in EXCLUDE_SET below.

    # =========================================================================
    # Serbo-Croatian (merge into Serbian)
    # =========================================================================
    "Serbo-Croatian": "Serbian",

    # =========================================================================
    # Montenegrin → Serbian (mutually intelligible; user's prior decision
    # was to merge Serbo-Croatian into Serbian — apply same policy)
    # =========================================================================
    # NOTE: leaving Montenegrin alone — only 2 records, distinct standard.
    # If user wants it merged, uncomment:
    # "Montenegrin": "Serbian",

    # =========================================================================
    # Sign languages — EXCLUDED per user policy. See EXCLUDE_SET below.
    # Previous entries removed: "Sign Language", "Swedish_Sign_Language",
    # "American Sign Language", "Swiss German Sign Language",
    # "Kazakh-Russian Sign Language".
    # =========================================================================

    # =========================================================================
    # Reunionese Creole variants
    # =========================================================================
    "Réunion Creole": "Reunionese Creole",
    "Reunion Creole": "Reunionese Creole",

    # =========================================================================
    # Greenlandic / Kalaallisut
    # =========================================================================
    "Kalaallisut": "Greenlandic",

    # =========================================================================
    # Komi-Zyrian variants
    # =========================================================================
    "Komi Zyrian": "Komi-Zyrian",

    # =========================================================================
    # Belarusian variants
    # =========================================================================
    "Belorussian": "Belarusian",

    # =========================================================================
    # Kirundi / Rundi
    # =========================================================================
    "Rundi": "Kirundi",

    # =========================================================================
    # Latin treebank-suffixed variants → Latin
    # =========================================================================
    "Latin PROIEL": "Latin",

    # =========================================================================
    # African American English
    # =========================================================================
    "African American Vernacular English": "African American English",

    # =========================================================================
    # Tagalog / Filipino — keep BOTH separate (sociolinguistically distinct
    # in many datasets) — no mapping.

    # =========================================================================
    # Hawaiian Pidgin (a creole, keep distinct from Hawaiian)
    # =========================================================================
    # No mapping needed — already distinct.

    # =========================================================================
    # Min variants — keep separate (each has its own ISO 639-3 code)
    # =========================================================================
    # Min Nan = nan, Min Dong = cdo  → no normalization

    # =========================================================================
    # Other ISO codes
    # =========================================================================
    "afr": "Afrikaans",
    "hau": "Hausa",
    "jav": "Javanese",
    "kin": "Kinyarwanda",
    "mar": "Marathi",
    "pcm": "Nigerian Pidgin",
    "sun": "Sundanese",
    "swe": "Swedish",
    "tat": "Tatar",
    "ukr": "Ukrainian",
    "vmw": "Makhuwa",
    "yor": "Yoruba",
    "amh": "Amharic",
    "tir": "Tigrinya",
    "som": "Somali",
    "orm": "Oromo",
    "ibo": "Igbo",
}

# =============================================================================
# 2. PROGRAMMING LANGUAGES: To be excluded
# =============================================================================
PROGRAMMING_LANGUAGES = {
    "Python", "Java", "C++", "C", "C#", "JavaScript", "TypeScript",
    "Go", "Ruby", "Rust", "PHP", "Scala", "Kotlin", "Swift", "Perl",
    "Lua", "R", "Julia", "Haskell", "Bash", "Shell", "HTML", "CSS",
    "SQL", "MATLAB", "Racket", "Objective-C", "Dart", "Groovy",
    "Assembly", "Fortran", "COBOL", "Prolog", "Lisp", "Erlang",
    "Clojure", "F#", "OCaml", "Scheme", "Smalltalk", "VHDL",
    "Verilog", "PowerShell", "Awk", "Sed",
    # Year-7 additions
    "OfficeScript",     # Microsoft Office automation language
    "Power Query M",    # Excel/Power BI formula language
    "Excel formulas",   # spreadsheet formulas
}

# =============================================================================
# 3a. SPLIT MAP: entries that should be expanded into multiple languages.
# These are data-entry artifacts where two languages got concatenated.
# Order in the value list determines insertion order.
# =============================================================================
SPLIT_MAP = {
    "Indonesian Hebrew": ["Indonesian", "Hebrew"],
}

SPLIT_MAP_CI = {k.lower(): v for k, v in SPLIT_MAP.items()}

# =============================================================================
# 4. EXCLUDE LIST: Non-languages to remove
# =============================================================================
EXCLUDE_SET = {
    # ---- Writing systems / scripts ----
    "Cyrillic", "CJK", "Latin script", "Latin", "Devanagari",
    "Arabic Script", "Baybayin", "Lontara", "Thaana", "Takri",
    "Prachalit", "Sylheti Nagri", "Linear B",
    "Hanja",              # Korean writing using Chinese characters
    "Ipa",                # International Phonetic Alphabet
    "Cretan Hieroglyphs", # writing system
    "Cuneiform",          # writing system (used for many languages)
    "Linear A",           # writing system (undeciphered)
    "Brahmi",             # writing system
    "Gurmukhi",           # writing system (used for Punjabi)
    "Modi",               # writing system (used for Marathi)
    "Ol Chiki",           # writing system (used for Santali)
    "Hiragana",           # writing system (Japanese)
    "Bopomofo",           # writing system (Mandarin phonetics)
    "Hangul",             # writing system (Korean)
    "Pegon",              # writing system (Javanese/Sundanese Arabic-based)
    "Nüshu",              # writing system (Chinese, women's script)
    "Pinyin",             # romanization system, not a language

    # ---- Language families / groupings (not individual languages) ----
    "Indo-European", "Sino-Tibetan", "Polynesian", "Uto-Aztecan",
    "Afro-Asiatic", "Afrasian", "Austronesian", "Niger-Congo",
    "Dravidian", "Turkic", "Uralic", "Malayo-Polynesian", "Hokan",
    "Mixe-Zoque", "Pama-Nyungan", "Trans-New Guinea",
    "Araucanian", "Oto-Manguean", "Mande",
    "Nilo-Saharan", "Edoid", "Kadai", "Mayan",
    "Romance languages", "Polynesian languages",
    "Slavic", "South-Slavic languages", "Celtic", "Iranian",
    "Kanak languages", "Kru languages",
    "Oceanic", "Gur", "Cahuapanan", "Totonacan",
    "Micronesian", "Kartvelian",
    "ObUgrian", "Franconian",
    "Bai dialects", "Chinese dialects",
    "Central Asian dialects",
    "Bantu",
    "Austronesian languages", "Uralic languages",
    "Baltic",  # language family / branch
    "Papuan languages",  # umbrella geographic grouping
    "Austroasiatic",     # family
    "Indic languages",   # family
    "Indic",             # family
    "African languages", # umbrella geographic grouping
    "Semitic languages", # family
    "Sámi languages",    # umbrella for the Sami group
    "Sami languages",    # ASCII variant of above
    "Sorbian",           # umbrella for Upper/Lower Sorbian, no own ISO code
    "Bihari",            # umbrella for Bhojpuri/Maithili/Magahi/Angika
    "Karen",             # umbrella for many Karen languages
    "Ryukyuan",          # family branch
    "East Asian languages",  # geographic umbrella
    "Asturleonese",      # umbrella for Asturian/Leonese/Mirandese
    "Bahasa",            # umbrella (means "language" in Malay)
    # Year-8 family/umbrella additions
    "Altaic",            # controversial / discredited family
    "Sinitic",           # family (Chinese branch)
    "Nahuatl languages", # umbrella
    "Bihari languages",  # umbrella
    "Bahnaric",          # family
    "To-tonacan",        # family

    # ---- Dataset / corpus / treebank tags that leaked in ----
    "l2-standard", "l2-perceived", "buckeye", "doreco", "voxangeles",
    "Syntagrus", "German PUD",
    "MiiPro",  # MiiPro is the name of a Japanese child-language corpus
    "Tanzil",  # Quran translation corpus
    "Ted",     # TED talks corpus
    "Qed",     # QED corpus (educational subtitles)
    "Arasaac", # ARASAAC pictogram set (AAC symbols, not a language)
    "Nanomuito",  # unknown — appears to be a data artifact

    # ---- Modalities (not languages) ----
    "Audio", "Video", "Acoustic", "Visual",

    # ---- Domains / topics (not languages) ----
    "Medical", "Music", "Twitter",
    "Medical Domain",
    "Biology", "Electronics", "Law",
    "Gis",          # GIS = Geographic Information Systems
    "CodeReview",   # Stack Exchange site / dataset tag

    # ---- Nationalities / regions / countries that aren't languages ----
    "East Asian", "Indian",
    "Singaporean", "Philippine", "Pakistani",
    "Colombian", "Malaysian",
    "Papua New Guinea", "Goroka",
    "Burkinabe",  # nationality, not a language
    "Argentinian",  # nationality
    "Arnhem",       # place (Arnhem Land, Australia)
    "Yaounde",      # place (capital of Cameroon)
    "Waigani",      # place in Papua New Guinea
    "Mauritania",   # country, not language
    # Year-7 nationality / region labels (no ISO code; per user policy:
    # exclude entirely, even when an Arabic dialect is implied)
    "Sudanese", "Bangladeshi", "Mexican",
    "Afghan", "Canadian", "Ghanaian", "Nigerian",
    "Tunisian", "Lebanese", "Qatari",
    "Grenadian", "Puerto Rican",
    "Ethiopian", "Eritrean", "Jewish",
    # Year-8 nationality labels
    "African",           # too generic
    "Belgian",           # nationality
    "Swiss",             # nationality
    "Kenyan",            # nationality
    "Roman",             # ancient/period label, not a language

    # ---- Other non-language entries ----
    "Mathematical Symbols", "Formal Languages",
    "Other Languages", "Other",
    "Unassigned", "Artificial",
    "Mixed Language", "non-English",
    "Khalisi",  # fictional (Game of Thrones)
    "Khalish",  # appears to be a typo/variant of "Khalisi" — fictional
    "Ice",      # not a language
    "Jaquar",   # typo / not a recognised language
    "Miwoc",    # typo (likely Miwok); excluded rather than guessed
    "Mathematics",  # not a language
    "Mongolia",     # country, not language
    # Scripts (additions for this round)
    "Glagolitic", "Katakana",
    # Language families / groupings (additions)
    "Romance", "Slavic languages",

    # ---- Code-mixed varieties (no own ISO 639-3 code) ----
    "Singlish", "Hinglish",
    "Code-mixed English-Hindi",
    "Bahasa Rojak",  # Malaysian English-Malay-Chinese-Tamil code-mixed

    # ---- Sign-language abbreviations (per sign-language exclusion policy) ----
    # The substring rule catches "X Sign Language" / "X Auslan" entries; these
    # bare abbreviations need explicit listing.
    "Bsl",  # British Sign Language
    "Lse",  # Lengua de Signos Española (Spanish Sign Language)

    # ---- Umbrella / non-specific labels ----
    "Philippine language",
    "Visayan languages",  # umbrella; "Visayan" → Cebuano via NORMALIZE_MAP

    # ---- Likely data-entry errors (no recognised language) ----
    "Dalkalaen", "Nahsta", "Bisakol", "Pani",
    "Pichwara",     # unknown — likely data error
    "Atezo", "Amr", "Hamta", "Iyara", "Bwasilaki", "Ganggalida",
    # Bare Chinese province names (ambiguous; could mean Mandarin or
    # any of the regional minority languages spoken there)
    "Sichuan", "Yunnan", "Hubei", "Henan",
    "Numma-guhooni",   # unknown
    "Arya",            # unclear / data error
    "Baharic",         # unknown / typo
    # Year-8 data errors / definitely-not-languages
    "Ptarmigan",       # a bird, not a language
    "Iroko",           # an African tree, not a language
    "Soto",            # too ambiguous (typo of Sesotho?); excluded
    "Aryan",           # ideological / vague
    "Carari",          # unknown
    "Sanna",           # unknown
    "Oro",             # ambiguous / data error
    "Chey",            # unknown / could be Cheyenne typo
    "Hexadecimal",     # encoding format
    "Emoji",           # not a language
    "Dyck-2",          # formal language theory
    "Expr",            # expression / programming
    "Point Cloud",     # 3D data format, not a language
    "Math",            # domain

    # ---- Religious-text / domain tags (not languages) ----
    "Koran",        # the Quran (religious text), not a language
    "Code",         # domain/programming-code tag
    "Subtitles",        # not a language — corpus type
    "Shakespearean",    # not a language — domain
    "American Literature",  # domain
    "Northeast Asian Archaeological Sites",  # domain
    "Others",       # umbrella placeholder
    "Hindustani Classical",  # music genre/domain
    "Turkish Makam",         # music form/domain

    # ---- Too-generic / ambiguous umbrellas ----
    "Pidgin",                  # ambiguous (Nigerian Pidgin? Tok Pisin? ...)
    "Creole",                  # ambiguous (which creole?)

    # ---- Code-mixed labels ----
    "CodeMixed",
    "CodeMix",

    # ---- Code-mixed language-pair labels ----
    "Komi-Zyrian-Russian",     # code-mixed Komi-Zyrian/Russian content

    # ---- Regional speech varieties without their own ISO 639-3 code ----
    # (Korean and Chinese sub-varieties: keep ones with ISO codes like
    #  Cantonese/Min Nan/Hakka/Jejueo elsewhere; exclude bare political/
    #  regional labels.)
    "North Korean", "South Korean",
    "Taiwanese",   # ambiguous regional label (Mandarin in Taiwan vs Min Nan)

    # ---- Language pairs (not individual languages) ----
    "English-Macedonian", "English-Albanian",
    "English-Spanish", "English-French",
    "English-German", "English-Chinese",
    "English-Arabic", "English-Hindi",
    "English-Japanese", "English-Korean",
    "English-Russian", "English-Portuguese",
    "English-Turkish", "English-Vietnamese",
    "English-Thai", "English-Indonesian",
    "Spanish-English", "French-English",
    "German-English", "Chinese-English",
    "Arabic-English", "Hindi-English",
    "Japanese-English", "Korean-English",
}

# =============================================================================
# 4a. EXCLUDE BY SUBSTRING: catches open-ended categories without needing to
# enumerate every variant. Applied case-insensitively.
#
# IMPORTANT: keep these substrings narrow enough that they don't match
# legitimate languages. E.g. "sign language" is safe because no spoken
# language has that phrase in its name.
# =============================================================================
EXCLUDE_SUBSTRINGS = (
    "sign language",   # excludes all sign languages (per user policy)
    "auslan",          # Australian Sign Language (variant abbreviation)
)

# =============================================================================
# 4b. REGIONAL VARIETY → PARENT LANGUAGE
# Pragmatic rule (per user): regional varieties without their own ISO 639-3
# code collapse to the parent (e.g. "Chilean Spanish" → "Spanish").
# Historical languages (Old English, Middle English, Old French, etc.) DO
# have ISO codes and are explicitly preserved.
# =============================================================================
REGIONAL_HISTORICAL_KEEPERS = {
    # These look like "<Adjective> <Language>" but are distinct historical
    # languages with ISO 639-3 codes — must be kept, not collapsed.
    "old english",          # ang
    "middle english",       # enm
    "early modern english",
    "old french",           # fro
    "middle french",        # frm
    "old high german",
    "middle high german",   # gmh
    "middle low german",    # gml
    "old saxon",            # osx
    "old church slavonic",  # chu
    "ancient greek",        # grc
    "old armenian",         # xcl
    "old irish",            # sga
    "old novgorodian",
    "old prussian",         # prg
    "old polish",
    "old east slavic",      # orv
    "old czech",
    "old sorbian",
    "old javanese",         # kaw
    "old tibetan",          # otb
    "classical tibetan",    # xct
    "classical arabic",     # arb (Standard Arabic macrolang)
    "classical syriac",     # syc
    "vedic sanskrit",       # has own corpus tradition, kept distinct
    "classical sanskrit",   # paired with Vedic Sanskrit
    # Year-9 additions: historical forms of regional-collapse-trigger languages
    "old spanish",          # osp — distinct historical language
    "old japanese",         # ojp — distinct historical language
    "middle japanese",      # ojp / variants — preempt future entries
    "old occitan",          # pro
    # Other multi-word "<Modifier> <Language>" entries that ARE distinct
    # languages with ISO codes:
    "african american english",  # aae
    "swiss german",              # gsw
    "crimean tatar",             # crh
    "molise croatian",           # svm
    "old béarnais", "modern béarnais",
    "old gascon", "modern gascon",
    # Sign languages are handled by EXCLUDE_SUBSTRINGS, no need to list here.
}

REGIONAL_PARENT_PATTERNS = {
    # parent language → tuple of substrings that, when matched
    # (case-insensitively), collapse the entry to the parent.
    # Entries in REGIONAL_HISTORICAL_KEEPERS bypass this.
    "English":  ("english",),
    "Spanish":  ("spanish",),
    "French":   ("french",),
    "Welsh":    ("welsh",),     # e.g. "Welsh (South Wales)" → Welsh
    "Japanese": ("japanese",),  # e.g. "Japanese (Hiragana)" → Japanese
}

# =============================================================================
# 5. Case-insensitive lookup helpers
# =============================================================================

def _build_case_insensitive_map(mapping):
    """Build a case-insensitive version of the normalization map."""
    ci_map = {}
    for k, v in mapping.items():
        ci_map[k.lower()] = v
    return ci_map


def _build_case_insensitive_set(s):
    """Build a case-insensitive version of a set."""
    return {item.lower() for item in s}


NORMALIZE_MAP_CI = _build_case_insensitive_map(NORMALIZE_MAP)
PROGRAMMING_CI = _build_case_insensitive_set(PROGRAMMING_LANGUAGES)
EXCLUDE_CI = _build_case_insensitive_set(EXCLUDE_SET)

# Known non-pairs: hyphenated names that are NOT language pairs
KNOWN_NON_PAIRS = {
    "komi-zyrian", "komi-ziran", "komi-permyak",
    "komi-zyrian-russian",  # mixed-language label, handled via EXCLUDE_SET below
    "min dong", "shipibo-konibo",
    "serbo-croatian", "kazakh-russian sign language",
    "guinea kpelle", "kok borok", "hiri motu",
    "cook islands maori", "cook islands māori",
    "sri lankan malay", "hawaiian pidgin",
    "haitian creole", "reunionese creole",
    "seychellois creole", "louisiana creole",
    "early new high german", "old church slavonic",
    "central bikol",
    "old-church-slavonic", "old_church_slavonic",
    "swedish_sign_language", "upper_sorbian", "north_sami",
    "middle-high-german",
    "kwak'wala",  # apostrophe-bearing, not a pair
    "mi'kmaq", "n'ko",
    "chin ngwan", "muak sa-aak",
    "swiss german", "min nan", "min bei",
    "coeur d'alene",
}


# =============================================================================
# 6. Helpers: ALL-CAPS detection
# =============================================================================

def _is_all_caps_phrase(s):
    """
    Return True if the string is in ALL CAPS (multiple words allowed) and
    contains at least one letter. Used as a heuristic to flag for casing
    normalization when no explicit mapping exists.
    """
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


# =============================================================================
# 7. Core cleanup logic
# =============================================================================

def is_language_pair(lang):
    """Check if a string looks like a language pair (e.g., 'English-French')."""
    if "-" not in lang:
        return False

    # Check against known non-pairs first
    if lang.lower() in KNOWN_NON_PAIRS:
        return False

    parts = lang.split("-")
    if len(parts) == 2:
        p1, p2 = parts[0].strip(), parts[1].strip()
        # Both parts start with uppercase and are multi-char → likely a pair
        if (len(p1) > 1 and p1[0].isupper() and
            len(p2) > 1 and p2[0].isupper()):
            return True

    return False


def clean_language(lang):
    """
    Clean a single language string.
    Returns the cleaned language name, or None if it should be excluded.

    Order of checks:
      1. Programming languages → exclude
      2. EXCLUDE_SET exact match → exclude
      3. EXCLUDE_SUBSTRINGS (e.g. "sign language") → exclude
      4. Language pairs (e.g. "English-French") → exclude
      5. NORMALIZE_MAP exact match → canonical form
      6. Regional varieties (e.g. "Chilean Spanish") → parent language
         (unless explicitly preserved as a historical/distinct language)
      7. Short ISO-code fallback
      8. ALL-CAPS fallback
    """
    lang = lang.strip()
    lang_lower = lang.lower()

    # 1. Exclude programming languages
    if lang_lower in PROGRAMMING_CI:
        return None

    # 2. Exclude non-language entries (exact match)
    if lang_lower in EXCLUDE_CI:
        return None

    # 3. Exclude by substring (catches all sign languages, etc.)
    #    Normalize underscores → spaces so "Swedish_Sign_Language" also matches.
    lang_lower_spaced = lang_lower.replace("_", " ")
    for sub in EXCLUDE_SUBSTRINGS:
        if sub in lang_lower_spaced:
            return None

    # 4. Exclude language pairs
    if is_language_pair(lang):
        return None

    # 5. Normalize known variants (case-insensitive)
    if lang_lower in NORMALIZE_MAP_CI:
        return NORMALIZE_MAP_CI[lang_lower]

    # 6. Regional-variety collapse to parent language
    #    (e.g. "Chilean Spanish" → "Spanish", "US English" → "English")
    #    Skip if this is an explicitly-preserved historical/distinct language.
    if lang_lower not in REGIONAL_HISTORICAL_KEEPERS:
        for parent, substrings in REGIONAL_PARENT_PATTERNS.items():
            if lang_lower == parent.lower():
                break  # exact match — it IS the parent, return below
            if any(sub in lang_lower for sub in substrings):
                return parent

    # 7. If it looks like a short ISO code (2-4 lowercase letters), try to resolve
    if len(lang) <= 4 and lang.isalpha() and lang == lang.lower():
        if lang_lower in NORMALIZE_MAP_CI:
            return NORMALIZE_MAP_CI[lang_lower]
        else:
            return None  # Unresolved ISO code

    # 8. Fallback: if the entry is ALL CAPS and not in the map, title-case it.
    if _is_all_caps_phrase(lang) and len(lang) > 1:
        return lang.title()

    return lang


def clean_languages(languages):
    """
    Clean a list of languages.
    Returns deduplicated list of cleaned language names and removed items.

    Some inputs (defined in SPLIT_MAP) expand into multiple languages —
    e.g. the data-entry artifact "Indonesian Hebrew" becomes
    ["Indonesian", "Hebrew"]. This expansion happens up-front, before
    per-item normalization, so each split-out language then runs through
    clean_language() normally.
    """
    # 1. First pass: expand split-cases.
    expanded = []
    for lang in languages:
        key = lang.strip().lower()
        if key in SPLIT_MAP_CI:
            expanded.extend(SPLIT_MAP_CI[key])
        else:
            expanded.append(lang)

    # 2. Second pass: clean each language individually.
    cleaned = []
    removed = []

    for lang in expanded:
        result = clean_language(lang)
        if result is not None:
            cleaned.append(result)
        else:
            removed.append(lang)

    # 3. Deduplicate while preserving order.
    seen = set()
    deduped = []
    for lang in cleaned:
        if lang not in seen:
            seen.add(lang)
            deduped.append(lang)

    return deduped, removed


def clean_record(record):
    """
    Clean the languages field of a single record.
    Returns the cleaned record and a change log dict.
    """
    original = record.get("languages", [])
    if not original:
        return record, None

    cleaned, removed = clean_languages(original)

    changes = None
    if cleaned != original:
        # Build normalized pairs for reporting.
        normalized = []
        for lang in original:
            key = lang.strip().lower()
            if key in SPLIT_MAP_CI:
                # Splits expand to multiple languages — report each separately
                # (each item in the split list is also run through clean_language
                # in case it needs further normalization, e.g. "Hebrew" → "Hebrew").
                split_targets = [
                    clean_language(x) or x for x in SPLIT_MAP_CI[key]
                ]
                normalized.append(
                    f"{lang} → {', '.join(split_targets)} (split)"
                )
                continue
            result = clean_language(lang)
            if result is not None and result != lang:
                normalized.append(f"{lang} → {result}")

        changes = {
            "title": record.get("title", "Unknown"),
            "original": original,
            "cleaned": cleaned,
            "removed": removed,
            "normalized": normalized,
        }

    record["languages"] = cleaned
    return record, changes


# =============================================================================
# 8. File I/O
# =============================================================================

def load_json_files(directory, recursive=True):
    """
    Load all JSON files from a directory, returning (filepath, data) pairs.
    """
    results = []
    base = Path(directory)
    pattern_fn = base.rglob if recursive else base.glob
    json_files = sorted(pattern_fn("*.json"))

    for filepath in json_files:
        # Skip summary/meta files
        if filepath.name.startswith("_"):
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append((filepath, data))
        except (json.JSONDecodeError, Exception) as e:
            print(f"  [WARN] Skipping {filepath}: {e}")

    return results


def save_json(filepath, data):
    """Save data to a JSON file with nice formatting. Creates parent dirs."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# 9. Reporting
# =============================================================================

def print_change_log(all_changes):
    """Print a detailed log of all changes made."""
    if not all_changes:
        print("\nNo changes were needed.")
        return

    print(f"\n{'=' * 70}")
    print(f" CHANGE LOG ({len(all_changes)} records modified)")
    print(f"{'=' * 70}")

    for i, change in enumerate(all_changes, 1):
        print(f"\n  [{i}] {change['title'][:80]}")
        print(f"      Before:     {change['original']}")
        print(f"      After:      {change['cleaned']}")
        if change["removed"]:
            print(f"      Removed:    {change['removed']}")
        if change["normalized"]:
            print(f"      Normalized: {change['normalized']}")


def print_before_after_counts(before_counter, after_counter):
    """Print side-by-side before/after language counts."""
    print(f"\n{'=' * 70}")
    print(f" BEFORE vs AFTER: Language Counts")
    print(f"{'=' * 70}")

    print(f"\n  Unique languages BEFORE: {len(before_counter)}")
    print(f"  Unique languages AFTER:  {len(after_counter)}")
    print(f"  Reduction: {len(before_counter) - len(after_counter)} entries consolidated\n")

    # Items removed entirely
    removed_langs = set(before_counter.keys()) - set(after_counter.keys())
    if removed_langs:
        print(f"  Languages/entries REMOVED ({len(removed_langs)}):")
        for lang in sorted(removed_langs):
            print(f"    ✗ {lang} (was {before_counter[lang]})")

    # Items added by normalization
    new_langs = set(after_counter.keys()) - set(before_counter.keys())
    if new_langs:
        print(f"\n  Languages ADDED via normalization ({len(new_langs)}):")
        for lang in sorted(new_langs):
            print(f"    + {lang} ({after_counter[lang]})")

    # Items whose counts changed
    changed = []
    for lang in sorted(after_counter.keys()):
        before = before_counter.get(lang, 0)
        after = after_counter[lang]
        if before != after and lang not in new_langs:
            changed.append((lang, before, after))

    if changed:
        print(f"\n  Languages with CHANGED counts ({len(changed)}):")
        for lang, before, after in changed:
            print(f"    ~ {lang}: {before} → {after} ({after - before:+d})")

    # Top languages after cleanup
    print(f"\n  Top 50 languages AFTER cleanup:")
    for i, (lang, count) in enumerate(after_counter.most_common(50), 1):
        print(f"    {i:3d}. {lang:<45} {count:4d}")

    # Show full list if more than 50
    remaining = after_counter.most_common()[50:]
    if remaining:
        print(f"\n  Remaining {len(remaining)} languages:")
        for i, (lang, count) in enumerate(remaining, 51):
            print(f"    {i:3d}. {lang:<45} {count:4d}")

    total_before = sum(before_counter.values())
    total_after = sum(after_counter.values())
    print(f"\n  Total occurrences BEFORE: {total_before}")
    print(f"  Total occurrences AFTER:  {total_after}")
    print(f"  Removed: {total_before - total_after}")


def export_csv(counter, output_path, field_name="item"):
    """Export counts to CSV."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"{field_name},count\n")
        for item, count in counter.most_common():
            item_escaped = f'"{item}"' if "," in item else item
            f.write(f"{item_escaped},{count}\n")
    print(f"  Exported to {output_path}")


# =============================================================================
# 10. Main
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up language fields in metadata JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (recommended first step) — walks subdirectories
  python cleanup_languages.py /path/to/json/files --dry-run --verbose

  # Top-level only (do NOT descend into subdirectories)
  python cleanup_languages.py /path/to/json/files --no-recursive

  # Apply changes in place
  python cleanup_languages.py /path/to/json/files

  # Apply changes to a separate directory (subdirectory structure preserved)
  python cleanup_languages.py /path/to/json/files --outdir cleaned/

  # Combined JSON file
  python cleanup_languages.py combined.json --combined --dry-run --verbose

  # Export CSV reports
  python cleanup_languages.py /path/to/json/files --export-csv --outdir results/
        """
    )
    parser.add_argument(
        "path",
        help="Directory of JSON files or a single combined JSON file"
    )
    parser.add_argument(
        "--combined", action="store_true",
        help="Treat path as a single combined JSON file"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--outdir", default=None,
        help="Write cleaned files to a separate directory (default: overwrite in place). Subdirectory structure is preserved."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed change log"
    )
    parser.add_argument(
        "--export-csv", action="store_true",
        help="Export before/after counts to CSV"
    )
    parser.add_argument(
        "--no-recursive", action="store_true",
        help="Do NOT descend into subdirectories (default: recursive)"
    )

    args = parser.parse_args()

    recursive = not args.no_recursive
    all_changes = []
    before_counter = Counter()
    after_counter = Counter()

    # ---- Combined JSON file ----
    if args.combined or os.path.isfile(args.path):
        with open(args.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = data if isinstance(data, list) else [data]
        print(f"Loaded {len(records)} records from {args.path}")

        for record in records:
            for lang in record.get("languages", []):
                before_counter[lang] += 1

            _, changes = clean_record(record)
            if changes:
                all_changes.append(changes)

            for lang in record.get("languages", []):
                after_counter[lang] += 1

        if not args.dry_run:
            outpath = args.path
            if args.outdir:
                os.makedirs(args.outdir, exist_ok=True)
                outpath = os.path.join(args.outdir, Path(args.path).name)

            save_json(outpath, data if isinstance(data, list) else records[0])
            print(f"Saved cleaned data to {outpath}")

    # ---- Directory of JSON files ----
    else:
        base = Path(args.path)
        file_data = load_json_files(args.path, recursive=recursive)
        mode = "recursively" if recursive else "(top-level only)"
        print(f"Loaded {len(file_data)} files from {args.path} {mode}")

        for filepath, data in file_data:
            records = data if isinstance(data, list) else [data]

            for record in records:
                for lang in record.get("languages", []):
                    before_counter[lang] += 1

                _, changes = clean_record(record)
                if changes:
                    all_changes.append(changes)

                for lang in record.get("languages", []):
                    after_counter[lang] += 1

            if not args.dry_run:
                if args.outdir:
                    rel = filepath.relative_to(base)
                    outpath = Path(args.outdir) / rel
                else:
                    outpath = filepath

                save_json(outpath, data)

        if not args.dry_run:
            dest = args.outdir or args.path
            print(f"Saved cleaned files to {dest}")

    # ---- Reporting ----
    if args.verbose:
        print_change_log(all_changes)

    print_before_after_counts(before_counter, after_counter)

    print(f"\n  Total records modified: {len(all_changes)}")

    if args.dry_run:
        print("\n  *** DRY RUN — No files were modified ***")

    # ---- Export CSV ----
    if args.export_csv:
        csv_dir = args.outdir or "."
        os.makedirs(csv_dir, exist_ok=True)
        export_csv(
            before_counter,
            os.path.join(csv_dir, "languages_before.csv"),
            "language"
        )
        export_csv(
            after_counter,
            os.path.join(csv_dir, "languages_after.csv"),
            "language"
        )


if __name__ == "__main__":
    main()