NAVIGATION = [
    {
        "label": "Fondasi",
        "items": [
            {"id": "brand", "label": "Brand"},
            {"id": "colors", "label": "Warna"},
            {"id": "typography", "label": "Tipografi"},
        ],
    },
    {
        "label": "Atom",
        "items": [
            {"id": "buttons", "label": "Button dan link"},
            {"id": "choices", "label": "Checkbox dan radio"},
            {"id": "chips-tags", "label": "Chip dan tag"},
            {"id": "toasts", "label": "Toast"},
        ],
    },
    {
        "label": "Molekul",
        "items": [
            {"id": "form-fields", "label": "Form field"},
            {"id": "accordion", "label": "Accordion"},
            {"id": "dropdown", "label": "Dropdown"},
            {"id": "panels-dialog", "label": "Panel dan dialog"},
        ],
    },
    {
        "label": "Application shell",
        "items": [{"id": "application-shell", "label": "Navbar dan footer"}],
    },
]


def _color(class_name, hex_value):
    return {
        "token": class_name.removeprefix("bg-"),
        "hex": hex_value,
        "class_name": class_name,
    }


COLOR_GROUPS = [
    {
        "label": "Primary",
        "usage": "Aksi utama, identitas, dan penekanan visual.",
        "colors": [
            _color("bg-primary-100", "#0c2f36"),
            _color("bg-primary-90", "#134954"),
            _color("bg-primary-80", "#1a6675"),
            _color("bg-primary-70", "#228396"),
            _color("bg-primary-60", "#29a0b7"),
            _color("bg-primary-50", "#37b9d2"),
            _color("bg-primary-40", "#61c8db"),
            _color("bg-primary-30", "#8ad6e5"),
            _color("bg-primary-20", "#b4e5ee"),
            _color("bg-primary-10", "#d5f0f6"),
        ],
    },
    {
        "label": "Secondary",
        "usage": "Elemen pendukung dan permukaan bernuansa teal.",
        "colors": [
            _color("bg-secondary-100", "#0c3733"),
            _color("bg-secondary-90", "#12544f"),
            _color("bg-secondary-80", "#19766f"),
            _color("bg-secondary-70", "#20978e"),
            _color("bg-secondary-60", "#28b9ae"),
            _color("bg-secondary-50", "#35d4c8"),
            _color("bg-secondary-40", "#5fddd3"),
            _color("bg-secondary-30", "#89e6df"),
            _color("bg-secondary-20", "#b3efe9"),
            _color("bg-secondary-10", "#d5f6f4"),
        ],
    },
    {
        "label": "Tertiary",
        "usage": "Aksen hijau untuk sustainability dan status positif.",
        "colors": [
            _color("bg-tertiary-100", "#192a1b"),
            _color("bg-tertiary-90", "#26402a"),
            _color("bg-tertiary-80", "#355a3a"),
            _color("bg-tertiary-70", "#44744b"),
            _color("bg-tertiary-60", "#538d5b"),
            _color("bg-tertiary-50", "#65a56e"),
            _color("bg-tertiary-40", "#85b78c"),
            _color("bg-tertiary-30", "#a5caaa"),
            _color("bg-tertiary-20", "#c5ddc9"),
            _color("bg-tertiary-10", "#dfece1"),
        ],
    },
    {
        "label": "Neutral",
        "usage": "Teks, divider, latar, dan elemen berprioritas rendah.",
        "colors": [
            _color("bg-neutral-100", "#333333"),
            _color("bg-neutral-90", "#4a4a4a"),
            _color("bg-neutral-80", "#606060"),
            _color("bg-neutral-70", "#777777"),
            _color("bg-neutral-60", "#8e8e8e"),
            _color("bg-neutral-50", "#a4a4a4"),
            _color("bg-neutral-40", "#bbbbbb"),
            _color("bg-neutral-30", "#d2d2d2"),
            _color("bg-neutral-20", "#e8e8e8"),
            _color("bg-neutral-10", "#ffffff"),
        ],
    },
    {
        "label": "Feedback & semantic",
        "usage": "Status, validasi, canvas, dan border aplikasi.",
        "colors": [
            _color("bg-red-10", "#ffb3b3"),
            _color("bg-red-20", "#ff8080"),
            _color("bg-red-30", "#ff0000"),
            _color("bg-red-70", "#ff383c"),
            _color("bg-warning-10", "#fff2b3"),
            _color("bg-warning-20", "#ffea80"),
            _color("bg-warning-30", "#998000"),
            _color("bg-surface-canvas", "#f4f7f2"),
            _color("bg-surface-subtle", "#edf7f0"),
            _color("bg-border-subtle", "#dce6df"),
        ],
    },
]

TYPOGRAPHY_GROUPS = [
    {
        "label": "Heading",
        "usage": "Poppins 700 untuk judul dan hierarki utama.",
        "items": [
            ("H1", "text-h1", "60px / 60px"),
            ("H2", "text-h2", "48px / 48px"),
            ("H3", "text-h3", "36px / 40px"),
            ("H4", "text-h4", "30px / 36px"),
            ("H5", "text-h5", "24px / 32px"),
            ("H6", "text-h6", "20px / 28px"),
            ("H7", "text-h7", "16px / 24px"),
            ("H8", "text-h8", "14px / 20px"),
            ("H9", "text-h9", "12px / 16px"),
        ],
    },
    {
        "label": "Sub-heading",
        "usage": "Inter 600 untuk label, kontrol, dan judul pendukung.",
        "items": [
            ("S1", "text-s1", "60px / 60px"),
            ("S2", "text-s2", "48px / 48px"),
            ("S3", "text-s3", "36px / 40px"),
            ("S4", "text-s4", "30px / 36px"),
            ("S5", "text-s5", "24px / 32px"),
            ("S6", "text-s6", "20px / 28px"),
            ("S7", "text-s7", "16px / 24px"),
            ("S8", "text-s8", "14px / 20px"),
            ("S9", "text-s9", "12px / 16px"),
        ],
    },
    {
        "label": "Body",
        "usage": "Inter 400 untuk isi, deskripsi, dan teks panjang.",
        "items": [
            ("B1", "text-b1", "60px / 60px"),
            ("B2", "text-b2", "48px / 48px"),
            ("B3", "text-b3", "36px / 40px"),
            ("B4", "text-b4", "30px / 36px"),
            ("B5", "text-b5", "24px / 32px"),
            ("B6", "text-b6", "20px / 28px"),
            ("B7", "text-b7", "16px / 24px"),
            ("B8", "text-b8", "14px / 20px"),
            ("B9", "text-b9", "12px / 16px"),
        ],
    },
]

TYPOGRAPHY_GROUPS = [
    {
        **group,
        "items": [
            {"token": token, "class_name": class_name, "metrics": metrics}
            for token, class_name, metrics in group["items"]
        ],
    }
    for group in TYPOGRAPHY_GROUPS
]

SNIPPETS = {
    "brand": '<a class="text-h5 text-primary-80">Sustaina<span class="text-tertiary-80">Bowl</span></a>',
    "colors": '<div class="bg-primary-80 text-neutral-10">Primary surface</div>\n<div class="bg-surface-subtle text-tertiary-80">Subtle surface</div>',
    "typography": '<h1 class="text-h1">Heading</h1>\n<p class="text-b7">Body copy</p>',
    "buttons": '{% include "components/button.html" with label="Simpan" variant="primary" icon_left="save" %}',
    "choices": '{% include "components/choice.html" with choice_type="checkbox" name="diet" value="vegan" label="Vegan" checked=True %}',
    "chips_tags": '<button class="ui-chip ui-chip--selected">Vegan</button>\n<span class="ui-tag ui-tag--warning">Peringatan</span>',
    "toasts": 'window.showToast("Perubahan tersimpan.", "success");',
    "form_fields": '{% include "components/form_field.html" with field=form.full_name variant="primary" %}',
    "accordion": '{% include "components/accordion.html" with label="Apa itu Eco Points?" content="Poin untuk pilihan ramah lingkungan." open=True %}',
    "dropdown": '{% include "components/dropdown.html" with label="Pilih kategori" items=dropdown_items %}',
    "panels_dialog": '<article class="ui-panel p-5">Panel content</article>\n<dialog class="ui-dialog p-6">Dialog content</dialog>',
    "application_shell": '{% include "header.html" %}\n{% block content %}{% endblock %}\n{% include "footer.html" %}',
}
