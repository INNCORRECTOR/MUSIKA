SITE_NAME = "MUSIKA"

# Same asset as site header/footer (email clients load via absolute URL).
BRAND_LOGO_URL = "https://musikazctech.s3.ap-south-1.amazonaws.com/musikalogo.webp"

# Footer “Built by” — logo file in /static (replace with your PNG/WebP if you prefer).
FOOTER_CREDIT_LOGO_URL = "/static/ZC-Insignia.webp"
FOOTER_CREDIT_URL = "https://zeliangcodetech.com/"

FOOTER_FACEBOOK_URL = "https://www.facebook.com/Musikaschool?mibextid=wwXIfr&mibextid=wwXIfr"
FOOTER_INSTAGRAM_URL = "https://www.instagram.com/musika_school?igsh=MXAyMWdwYTAybG1mZw=="
FOOTER_YOUTUBE_URL = "https://youtube.com/@musikanagaland?si=rwV1KhHTqJbjeYZG"

NAV_ITEMS = [
    {"label": "Home", "href": "/"},
    {"label": "About", "href": "/about"},
    {"label": "Faculty", "href": "/artist"},
    {"label": "Courses", "href": "/course"},
    {"label": "Events", "href": "/event"},
    {"label": "Gallery", "href": "/gallery"},
    {"label": "Contact", "href": "/contact"},
]

PAGE_CONTENTS = {
    "artist": {
        "title": "Faculty",
        "intro": "Meet some of the talented artistes currently developing and performing with MUSIKA.",
        "sections": [
            "Ari Nova - Afro-fusion vocalist and songwriter.",
            "Kairo Beats - Producer and live performance DJ.",
            "Luna Vox - Alternative soul artist and guitarist.",
            "Miko Ray - Hip-hop lyricist and stage performer.",
        ],
    },
    "course": {
        "title": "Course",
        "intro": "Explore practical courses designed for beginners and advancing artists.",
        "sections": [
            "Music Production Fundamentals - DAW workflow, arrangement, and mixing basics.",
            "Songwriting Lab - melody development, lyric structure, and composition techniques.",
            "Vocal Performance - breath control, tone, projection, and live confidence.",
            "Artist Branding - storytelling, visual identity, and audience growth strategy.",
        ],
    },
    "event": {
        "title": "Event",
        "intro": "Stay updated with showcases, workshops, and community sessions.",
        "sections": [
            "Open Mic Fridays - Weekly artist showcase and audience feedback.",
            "Producer Circle - Collaborative beat-making and critique sessions.",
            "MUSIKA Live Nights - Curated performances from roster artists.",
            "Industry Talk Series - Guest sessions with managers and producers.",
        ],
    },
    "gallery": {
        "title": "Gallery",
        "intro": "A visual collection of performances, studio sessions, and community stories.",
        "sections": [
            "Live stage moments from MUSIKA showcase nights.",
            "Backstage and rehearsal highlights from our artists.",
            "Workshop snapshots and student achievement features.",
        ],
    },
    "contact": {
        "title": "Contact",
        "intro": "Connect with MUSIKA for admissions, artist opportunities, partnerships, and events.",
        "sections": [
            "Email: musikaschool06@gmail.com",
            "Phone: +91 98568 63879, +91 94360 07979",
            "Address: Dimapur, Nagaland, India",
            "Office Hours: Monday - Saturday, 11 AM - 6 PM",
        ],
    },
}
