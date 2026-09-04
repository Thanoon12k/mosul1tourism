"""Bilingual website for Harith Firas — Mosul tourism and travel services."""

from __future__ import annotations

import os
from urllib.parse import quote

from flask import Flask, jsonify, render_template

app = Flask(__name__)


def whatsapp(number: str, message: str) -> str:
    """Create a WhatsApp deep link with a pre-filled message."""
    return f"https://wa.me/{number}?text={quote(message)}"


SERVICES = [
    {
        "number": "01", "slug": "tours", "image": "gallery/gallery-05.jpg",
        "title_ar": "جولات سياحية مع مرشد محلي", "title_en": "Guided tours with a local expert",
        "summary_ar": "اكتشف الموصل القديمة ونينوى وباقي مواقع العراق مع حارث؛ جولات خاصة ومجموعات وبالعربية أو الإنكليزية.",
        "summary_en": "Discover old Mosul, Nineveh and destinations across Iraq with Harith—private or group tours in Arabic or English.",
        "features_ar": ["برامج خاصة حسب الوقت والاهتمامات", "استقبال ومرافقة الضيوف الأجانب", "تنسيق النقل والتذاكر داخل الرحلة"],
        "features_en": ["Itineraries tailored to your time and interests", "Hosting and guiding international visitors", "Trip transport and ticket coordination"],
        "phone": "+964 772 644 3352",
        "wa_ar": whatsapp("9647726443352", "السلام عليكم حارث، أريد الاستفسار عن جولة سياحية في الموصل.\nالخدمة: جولة خاصة مع مرشد سياحي\nعدد الأشخاص: \nالتاريخ المطلوب: \nاللغة: \nالمواقع التي أرغب بزيارتها: "),
        "wa_en": whatsapp("9647726443352", "Hello Harith, I would like to ask about a guided tour in Mosul.\nService: Private guided tour\nNumber of guests: \nPreferred date: \nLanguage: \nPlaces I would like to visit: "),
    },
    {
        "number": "02", "slug": "umrah", "image": "poster-jeddah-gulf-cup.jpg",
        "title_ar": "الحج والعمرة والرحلات الدينية", "title_en": "Hajj, Umrah & religious journeys",
        "summary_ar": "برامج عمرة برية منظمة من الموصل تشمل التأشيرة والنقل والسكن والزيارات الدينية وفق تفاصيل كل رحلة.",
        "summary_en": "Organized overland Umrah programs from Mosul, including visa, transport, accommodation and religious visits as listed per trip.",
        "features_ar": ["الانطلاق من الموصل", "فنادق في مكة والمدينة", "متابعة وتنقلات ضمن البرنامج"],
        "features_en": ["Departure from Mosul", "Hotels in Makkah and Madinah", "Program support and local transfers"],
        "phone": "+964 787 820 5040",
        "wa_ar": whatsapp("9647878205040", "السلام عليكم حارث، أريد الاستفسار عن برنامج الحج أو العمرة.\nنوع الرحلة: \nعدد المسافرين: \nتاريخ السفر: \nملاحظات: "),
        "wa_en": whatsapp("9647878205040", "Hello Harith, I would like to ask about a Hajj or Umrah program.\nTrip type: \nNumber of travelers: \nPreferred date: \nNotes: "),
    },
    {
        "number": "03", "slug": "hotels", "image": "hotels/ramada-mosul.avif",
        "title_ar": "حجز وتأجير الفنادق", "title_en": "Hotel booking & accommodation",
        "summary_ar": "مساعدة مباشرة لاختيار وحجز السكن المناسب في الموصل حسب عدد الضيوف والميزانية ومدة الإقامة.",
        "summary_en": "Direct help choosing and booking suitable accommodation in Mosul based on group size, budget and length of stay.",
        "features_ar": ["خيارات للأفراد والعوائل والمجموعات", "مقارنة حسب الموقع والميزانية", "تأكيد التفاصيل عبر واتساب"],
        "features_en": ["Options for solo guests, families and groups", "Choice by location and budget", "Details confirmed directly on WhatsApp"],
        "phone": "+964 771 061 3674", "secondary_phone": "+964 751 713 4731",
        "wa_ar": whatsapp("9647710613674", "السلام عليكم، أريد حجز فندق في الموصل.\nعدد الضيوف: \nتاريخ الوصول: \nتاريخ المغادرة: \nالميزانية التقريبية: \nملاحظات: "),
        "wa_en": whatsapp("9647710613674", "Hello, I would like to book a hotel in Mosul.\nNumber of guests: \nCheck-in date: \nCheck-out date: \nApproximate budget: \nNotes: "),
    },
]


HOTELS = [
    {
        "slug": "ramada-mosul", "image": "hotels/ramada-mosul.avif", "stars": 5,
        "name_ar": "رامادا بلازا باي ويندهام الموصل كورنيش", "name_en": "Ramada Plaza by Wyndham Mosul Corniche",
        "rating_ar": "فئة فاخرة · 5 نجوم", "rating_en": "Luxury category · 5 stars",
        "location_ar": "الضفة الغربية · كورنيش دجلة", "location_en": "West Bank · Tigris Corniche",
        "rate_ar": "120–180 دولاراً / الليلة", "rate_en": "$120–$180 / night",
        "summary_ar": "خيار فاخر بإطلالات على دجلة ومرافق متكاملة، مناسب لرحلات الأعمال والضيوف الباحثين عن إقامة راقية.",
        "summary_en": "An upscale riverside option with full facilities, suited to business trips and guests seeking a premium stay.",
        "amenities_ar": ["148 غرفة وجناحاً", "مطعم وخدمة غرف على مدار الساعة", "نادي رياضي وساونا وقاعات اجتماعات"],
        "amenities_en": ["148 rooms and suites", "Restaurant and 24-hour room service", "Gym, sauna and meeting rooms"],
        "source": "https://www.wyndhamhotels.com/ramada/mosul-iraq/ramada-plaza-mosul-corniche/overview",
    },
    {
        "slug": "white-tower", "image": "hotels/white-tower.jpg", "stars": 4,
        "name_ar": "فندق البرج الأبيض", "name_en": "White Tower Hotel",
        "rating_ar": "فئة متوسطة · 4 نجوم", "rating_en": "Midscale category · 4 stars",
        "location_ar": "شمال وسط الموصل", "location_en": "North-Central Mosul",
        "rate_ar": "90–110 دولارات / الليلة", "rate_en": "$90–$110 / night",
        "summary_ar": "فندق حديث يناسب المسافرين المستقلين والعوائل والمجموعات السياحية، مع غرف وأجنحة عائلية.",
        "summary_en": "A modern hotel for independent travelers, families and tour groups, with rooms and family-sized suites.",
        "amenities_ar": ["غرف وأجنحة عائلية", "ساونا وجاكوزي", "إفطار وموقف سيارات وخدمة استقبال 24 ساعة"],
        "amenities_en": ["Rooms and family suites", "Sauna and jacuzzi", "Breakfast, parking and 24-hour reception"],
        "source": "https://www.skyscanner.qa/hotels/iraq/mosul-hotels/%D9%81%D9%86%D8%AF%D9%82-%D8%A7%D9%84%D8%A8%D8%B1%D8%AC-%D8%A7%D9%84%D8%A8%D9%8A%D8%B6-white-tower-hotel/ht-228302228",
    },
    {
        "slug": "modern-palace", "image": "hotels/modern-palace.webp", "stars": 4,
        "name_ar": "فندق القصر الحديث · مودرن بلازا", "name_en": "Modern Palace Hotel · Modern Plaza",
        "rating_ar": "فئة تجارية · 3–4 نجوم", "rating_en": "Commercial category · 3–4 stars",
        "location_ar": "الدواسة والفيصلية", "location_en": "Al-Dawasa & Al-Faisaliyah",
        "rate_ar": "45–70 دولاراً / الليلة", "rate_en": "$45–$70 / night",
        "summary_ar": "إقامة عملية في قلب المركز التجاري للموصل، مناسبة للصحفيين والوفود والمسافرين بميزانية مدروسة.",
        "summary_en": "A practical stay in Mosul's commercial center for journalists, delegations and budget-conscious travelers.",
        "amenities_ar": ["غرف بحمامات خاصة وتكييف", "إنترنت ومطعم تقليدي", "تنسيق المطار وسيارات الأجرة عند الطلب"],
        "amenities_en": ["En-suite rooms with climate control", "Wi-Fi and a traditional restaurant", "Airport and taxi coordination on request"],
        "source": "https://iraqiguide.com/hotel/modern-plaza-international-hotel",
    },
    {
        "slug": "abraj-al-madina", "image": "hotels/abraj-al-madina.webp", "stars": 4,
        "name_ar": "فندق أبراج المدينة", "name_en": "Abraj Al Madina Hotel",
        "rating_ar": "فئة بوتيك · 3–4 نجوم", "rating_en": "Boutique category · 3–4 stars",
        "location_ar": "الفيصلية · الساحل الأيسر", "location_en": "Al-Faisaliyah · East Bank",
        "rate_ar": "60–80 دولاراً / الليلة", "rate_en": "$60–$80 / night",
        "summary_ar": "إقامة حديثة قرب المطاعم والمقاهي والأسواق المسائية، ملائمة للعوائل وزوار الساحل الأيسر.",
        "summary_en": "A modern stay near restaurants, cafés and evening shopping, convenient for families and East Bank visitors.",
        "amenities_ar": ["غرف حديثة مع مصعد وتكييف", "تلفاز وثلاجة صغيرة وضيافة", "إفطار بوفيه وخدمة ضيوف 24 ساعة"],
        "amenities_en": ["Modern elevator-served rooms", "TV, mini-fridge and refreshment station", "Buffet breakfast and 24-hour guest service"],
        "source": "https://abrajalmadina.com/?lang=ar",
    },
    {
        "slug": "al-baron", "image": "hotels/al-baron.jfif", "stars": 3,
        "name_ar": "فندق البارون", "name_en": "Al-Baron Hotel",
        "rating_ar": "فئة قياسية · 3 نجوم", "rating_en": "Standard category · 3 stars",
        "location_ar": "وسط الموصل", "location_en": "Central Mosul",
        "rate_ar": "45–65 دولاراً / الليلة", "rate_en": "$45–$65 / night",
        "summary_ar": "خيار اقتصادي مرتب للإقامات القصيرة والمسافرين المستقلين، قريب بالسيارة من المدينة القديمة.",
        "summary_en": "A tidy value option for short stays and independent travelers, a quick drive from the old city.",
        "amenities_ar": ["غرف عملية بحمامات خاصة", "تكييف وتدفئة وإنترنت", "استقبال 24 ساعة وحفظ أمتعة"],
        "amenities_en": ["Functional rooms with private bathrooms", "Air conditioning, heating and Wi-Fi", "24-hour reception and luggage storage"],
        "source": "https://www.traveloka.com/en-en/hotel/asia/al-baron-hotel-mosul-9000006204301",
    },
]

for hotel in HOTELS:
    hotel["wa_ar"] = whatsapp(
        "9647710613674",
        f"السلام عليكم، أريد الاستفسار عن حجز {hotel['name_ar']}.\nتاريخ الوصول: \nتاريخ المغادرة: \nعدد الضيوف: \nنوع الغرفة: \nملاحظات: ",
    )
    hotel["wa_en"] = whatsapp(
        "9647710613674",
        f"Hello, I would like to ask about booking {hotel['name_en']}.\nCheck-in date: \nCheck-out date: \nNumber of guests: \nRoom type: \nNotes: ",
    )


LANDMARKS = [
    {
        "slug": "al-nuri", "image": "mosul/al-nuri-2025.jpg",
        "title_ar": "جامع النوري ومنارة الحدباء", "title_en": "Al-Nuri Mosque & Al-Hadba Minaret",
        "kicker_ar": "قلب المدينة القديمة", "kicker_en": "Heart of the old city",
        "description_ar": "أحد أشهر رموز الهوية الموصلية، يروي تاريخ العمارة والحياة في أزقة المدينة القديمة.",
        "description_en": "One of Mosul’s defining symbols, telling the story of its architecture and old-city life.",
        "credit": "الدبوني · CC BY-SA 4.0", "source": "https://commons.wikimedia.org/wiki/File:Great_Mosque_of_al-Nuri_Feb_2025_3.jpg",
    },
    {
        "slug": "clock-church", "image": "mosul/clock-church-2024.jpg",
        "title_ar": "كنيسة الساعة", "title_en": "Our Lady of the Hour Church",
        "kicker_ar": "برج يروي الزمن", "kicker_en": "A tower that tells time",
        "description_ar": "معلم بارز في النسيج التاريخي للموصل القديمة، ببرج ساعته وحضوره المعماري الفريد.",
        "description_en": "A landmark of old Mosul, known for its clock tower and distinctive architectural presence.",
        "credit": "الدبوني · CC BY-SA 4.0", "source": "https://commons.wikimedia.org/wiki/File:Our_Lady_of_the_Hour_Church.jpg",
    },
    {
        "slug": "al-tahira", "image": "mosul/al-tahira-2025.jpg",
        "title_ar": "كنيسة الطاهرة التحتانية", "title_en": "Al-Tahira al-Tahtaniyya Church",
        "kicker_ar": "تراث حي وتعايش", "kicker_en": "Living heritage & coexistence",
        "description_ar": "فضاء تراثي داخل المدينة القديمة يعكس تنوع الموصل وعمق عمارتها الدينية.",
        "description_en": "A heritage space in the old city reflecting Mosul’s diversity and deep religious architecture.",
        "credit": "الدبوني · CC BY-SA 4.0", "source": "https://commons.wikimedia.org/wiki/File:Al-Tahira_al-Tahtaniyya_Church_Mosul.jpg",
    },
    {
        "slug": "river-gate", "image": "mosul/river-gate-2019.jpg",
        "title_ar": "باب الشط", "title_en": "The River Gate — Bab al-Shatt",
        "kicker_ar": "من المدينة إلى دجلة", "kicker_en": "From the city to the Tigris",
        "description_ar": "إحدى بوابات الموصل التاريخية المطلة باتجاه النهر، وبصمة باقية من سور المدينة القديمة.",
        "description_en": "A historic Mosul gate facing the river and a surviving trace of the old city wall.",
        "credit": "MosulEye · CC BY 4.0", "source": "https://commons.wikimedia.org/wiki/File:Mosul_-_The_river%27s_gate.jpg",
    },
    {
        "slug": "bashtabia", "image": "mosul/bashtabia-2014.jpg",
        "title_ar": "قلعة باشطابيا", "title_en": "Bash Tapia Castle",
        "kicker_ar": "حارسة الضفة القديمة", "kicker_en": "Guardian of the old bank",
        "description_ar": "من بقايا تحصينات الموصل وسورها التاريخي على ضفة دجلة، ومشهد يرتبط بذاكرة المدينة.",
        "description_en": "Remains of Mosul’s historic fortifications and wall on the Tigris, tied to the city’s memory.",
        "credit": "Eng Omer Akram · CC BY-SA 4.0", "source": "https://commons.wikimedia.org/wiki/File:Bashtabia.jpg",
    },
    {
        "slug": "museum", "image": "mosul/mosul-museum.jpg",
        "title_ar": "متحف الموصل الحضاري", "title_en": "Mosul Cultural Museum",
        "kicker_ar": "بوابة حضارات نينوى", "kicker_en": "Gateway to Nineveh’s civilizations",
        "description_ar": "محطة أساسية لفهم تاريخ نينوى والموصل وما تركته حضارات وادي الرافدين من فن وآثار.",
        "description_en": "An essential stop for understanding Nineveh, Mosul and the art and archaeology of Mesopotamia.",
        "credit": "Iraqi government archive · Public domain", "source": "https://commons.wikimedia.org/wiki/File:Mosul_Cultural_Museum.jpg",
    },
    {
        "slug": "mashki", "image": "mosul/mashki-gate-1990.jpg",
        "title_ar": "بوابة مشكي — نينوى", "title_en": "Mashki Gate — Nineveh",
        "kicker_ar": "صورة أرشيفية", "kicker_en": "Archive photograph",
        "description_ar": "بوابة من سور نينوى الآشورية؛ تظهر هنا في صورة أرشيفية من عام 1990 قبل الأحداث اللاحقة.",
        "description_en": "A gate in the Assyrian wall of Nineveh, shown here in a 1990 archive photograph before later events.",
        "credit": "Fredarch · CC BY-SA 3.0", "source": "https://commons.wikimedia.org/wiki/File:Nineveh_mashki_gate_from_west.JPG",
    },
    {
        "slug": "pasha", "image": "mosul/pasha-mosque-2019.jpg",
        "title_ar": "جامع الباشا والمدينة القديمة", "title_en": "Pasha Mosque & the Old City",
        "kicker_ar": "أزقة من حجر وذاكرة", "kicker_en": "Alleys of stone and memory",
        "description_ar": "مشهد من نسيج الموصل القديمة حيث تتجاور الأزقة والأسواق ودور العبادة في حكاية واحدة.",
        "description_en": "A view into old Mosul, where alleys, markets and places of worship share one urban story.",
        "credit": "Levi Clancy · CC0", "source": "https://commons.wikimedia.org/wiki/File:Views_of_Pasha_Mosque_in_the_old_city_of_Mosul_in_the_summer_of_2019,_after_war_with_the_Islamic_State_24.jpg",
    },
    {
        "slug": "tigris", "image": "mosul/tigris-2019.jpg",
        "title_ar": "نهر دجلة", "title_en": "The Tigris River",
        "kicker_ar": "نبض الموصل", "kicker_en": "Mosul’s pulse",
        "description_ar": "النهر الذي يقسم الموصل إلى جانبيها ويربط الجسور والأسواق والذاكرة اليومية للمدينة.",
        "description_en": "The river dividing Mosul’s two banks while connecting its bridges, markets and everyday memory.",
        "credit": "Levi Clancy · CC0", "source": "https://commons.wikimedia.org/wiki/File:Views_along_the_river_Tigris_in_Mosul_in_2019_when_Moslawis_go_during_the_summer_to_cool_down_01.jpg",
    },
]


GALLERY_IMAGES = [
    {"file": "gallery-01.jpg", "alt_ar": "حارث فراس بقميص العراق 2026", "alt_en": "Harith Firas in an Iraq 2026 shirt", "category": "iraq sports"},
    {"file": "gallery-02.jpg", "alt_ar": "لقاء خلال إحدى الرحلات العربية", "alt_en": "A meeting during an Arab journey", "category": "iraq guests"},
    {"file": "gallery-03.jpg", "alt_ar": "حارث فراس خلال السفر", "alt_en": "Harith Firas while traveling", "category": "travel"},
    {"file": "gallery-04.jpg", "alt_ar": "حارث فراس مع سائح أجنبي في العراق", "alt_en": "Harith with an international tourist in Iraq", "category": "iraq guests"},
    {"file": "gallery-05.jpg", "alt_ar": "جولة مع مجموعة سياح أجانب", "alt_en": "A tour with international visitors", "category": "iraq guests"},
    {"file": "gallery-06.jpg", "alt_ar": "لحظة مميزة مع ضيوف العراق", "alt_en": "A memorable moment with guests in Iraq", "category": "iraq guests"},
    {"file": "gallery-07.jpg", "alt_ar": "حارث في ملعب كرة قدم خلال رحلة جماهيرية", "alt_en": "Harith at a stadium during a fan trip", "category": "sports"},
    {"file": "gallery-08.jpg", "alt_ar": "حارث فراس خلال تنظيم جولة", "alt_en": "Harith Firas organizing a tour", "category": "iraq travel"},
    {"file": "gallery-09.jpg", "alt_ar": "ضيافة عربية خلال إحدى الرحلات", "alt_en": "Arab hospitality during a trip", "category": "travel guests"},
    {"file": "gallery-10.jpg", "alt_ar": "حارث فراس في إسطنبول", "alt_en": "Harith Firas in Istanbul", "category": "turkey"},
    {"file": "gallery-11.jpg", "alt_ar": "بوستر رحلة الموصل إلى جدة والعمرة وكأس الخليج", "alt_en": "Mosul–Jeddah Umrah and Gulf Cup trip poster", "category": "posters sports umrah"},
    {"file": "gallery-12.jpg", "alt_ar": "حارث فراس في رحلة بحرية", "alt_en": "Harith Firas on a waterside journey", "category": "turkey travel"},
    {"file": "gallery-13.jpg", "alt_ar": "بوستر برنامج إسطنبول الكبرى", "alt_en": "Grand Istanbul program poster", "category": "posters turkey"},
    {"file": "gallery-14.jpg", "alt_ar": "إطلالة من إسطنبول", "alt_en": "A view from Istanbul", "category": "turkey"},
    {"file": "gallery-15.jpg", "alt_ar": "جولة سياحية أمام معلم عثماني", "alt_en": "A tour at an Ottoman landmark", "category": "turkey guests"},
    {"file": "gallery-16.jpg", "alt_ar": "لقاء مرح مع أحد ضيوف العراق", "alt_en": "A cheerful meeting with a guest in Iraq", "category": "iraq guests"},
    {"file": "gallery-17.jpg", "alt_ar": "حارث مع سائح أمام بوابة عشتار في بابل", "alt_en": "Harith with a visitor at the Ishtar Gate in Babylon", "category": "iraq guests"},
    {"file": "gallery-18.jpg", "alt_ar": "رحلة حارث فراس إلى إسطنبول", "alt_en": "Harith Firas in Istanbul", "category": "turkey"},
    {"file": "gallery-19.jpg", "alt_ar": "حارث فراس في أجواء شتوية", "alt_en": "Harith Firas in winter scenery", "category": "turkey travel"},
    {"file": "gallery-20.jpg", "alt_ar": "حارث وسط أجواء مباراة جماهيرية", "alt_en": "Harith amid a football crowd", "category": "sports"},
    {"file": "gallery-21.jpg", "alt_ar": "صورة من تغطية إسطنبول", "alt_en": "A scene from Istanbul coverage", "category": "turkey"},
    {"file": "gallery-22.jpg", "alt_ar": "من بلاد الرافدين إلى كأس العالم", "alt_en": "From Mesopotamia to the World Cup", "category": "sports iraq"},
    {"file": "gallery-23.jpg", "alt_ar": "حارث خلال إحدى الرحلات الخارجية", "alt_en": "Harith on an international journey", "category": "travel"},
    {"file": "gallery-24.jpg", "alt_ar": "بوستر رحلة تركيا بعين مختلفة", "alt_en": "Turkey through a different lens poster", "category": "posters turkey"},
]


CURRENT_TRIP = {
    "wa_ar": whatsapp("9647878205040", "السلام عليكم حارث، أريد حجز رحلة العمرة وكأس الخليج في جدة بتاريخ 19/9/2026.\nعدد المسافرين: \nفئة تذكرة المباراة: \nالمدينة: \nملاحظات: "),
    "wa_en": whatsapp("9647878205040", "Hello Harith, I would like to book the Umrah and Gulf Cup trip to Jeddah departing 19 September 2026.\nNumber of travelers: \nMatch ticket category: \nCity: \nNotes: "),
}


@app.get("/")
def home():
    return render_template(
        "index.html",
        services=SERVICES,
        hotels=HOTELS,
        landmarks=LANDMARKS,
        gallery_images=GALLERY_IMAGES,
        current_trip=CURRENT_TRIP,
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
