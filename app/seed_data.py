"""Sample knowledge for each niche. Every template is a SAMPLE – replace with the owner's details."""

from __future__ import annotations

SAMPLE_LABEL = "Sample – replace with owner's details"

TEMPLATES: dict[str, dict] = {
    "dental_clinic": {
        "sample_business": "Smile Care Dental (Anna Nagar, Chennai)",
        "knowledge": {
            "address": "Smile Care Dental, 2nd Floor, 14 Shanthi Colony Main Road, Anna Nagar, Chennai 600040 (above Apollo Pharmacy). Google Maps: search 'Smile Care Dental Anna Nagar'.",
            "timings": "Mon–Sat: 10:00 AM – 1:30 PM and 5:00 PM – 9:00 PM. Sunday: 10:00 AM – 1:00 PM (appointments only).",
            "services": "\n".join(
                [
                    "Consultation & check-up: ₹300",
                    "Scaling & polishing (cleaning): ₹1,200",
                    "Tooth-coloured filling: from ₹1,000 per tooth",
                    "Root canal treatment (RCT): from ₹4,500 per tooth",
                    "Tooth extraction (simple): ₹800",
                    "Wisdom tooth removal (surgical): from ₹4,000",
                    "Ceramic crown (cap): from ₹6,500",
                    "Zirconia crown: from ₹12,000",
                    "Teeth whitening (in-clinic): ₹8,000",
                    "Clear aligners: from ₹75,000 (after consultation)",
                    "Metal braces: from ₹35,000",
                    "Kids dental check-up: ₹300",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Do you accept walk-ins? A: Yes, but appointments get priority. Book on WhatsApp to avoid waiting.",
                    "Q: Is parking available? A: Two-wheeler parking in front; car parking on Shanthi Colony road.",
                    "Q: Payment options? A: UPI, cards and cash. EMI available for aligners and braces through the clinic.",
                    "Q: Is RCT painful? A: It is done under local anaesthesia. The doctor will explain everything at consultation.",
                    "Q: Do you treat children? A: Yes, we see kids from 3 years for check-ups and fillings.",
                    "Q: Is the consultation fee adjusted in treatment? A: Yes, if treatment starts the same day.",
                ]
            ),
            "booking_instructions": "Collect: patient name, age, problem in a few words, preferred date and time (morning or evening). Repeat details back and say the front desk will confirm the slot on WhatsApp.",
            "rules": "Never diagnose or say what treatment is needed. Never suggest medicines or painkillers. Never promise pain-free or guaranteed results. Hand over for: severe pain, swelling, bleeding, broken tooth or accident (emergency), insurance questions, complaints, requests to speak to the doctor.",
            "handoff_contact": "Front desk: +91 98400 12345",
            "tone": "Warm, reassuring and professional. Use 'Sir/Madam' politely. Short sentences.",
        },
    },
    "salon": {
        "sample_business": "Glow Studio Unisex Salon (Velachery, Chennai)",
        "knowledge": {
            "address": "Glow Studio Unisex Salon, 45 Taramani Link Road, Velachery, Chennai 600042 (opposite Phoenix MarketCity Gate 2).",
            "timings": "All days: 10:00 AM – 9:00 PM. Last appointment at 8:00 PM.",
            "services": "\n".join(
                [
                    "Men's haircut: ₹300",
                    "Men's haircut + beard styling: ₹450",
                    "Women's haircut: from ₹600",
                    "Hair spa: from ₹1,200",
                    "Global hair colour (women): from ₹3,500",
                    "Root touch-up: ₹1,500",
                    "Keratin treatment: from ₹5,500",
                    "Clean-up facial: ₹900",
                    "Gold facial: ₹2,200",
                    "Full arms waxing (Rica): ₹600",
                    "Manicure: ₹600 | Pedicure: ₹800",
                    "Bridal makeup: from ₹15,000 (trial extra)",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Do I need an appointment? A: Walk-ins are welcome, but weekends get busy, so booking is better.",
                    "Q: Which products do you use? A: L'Oréal Professionnel, Schwarzkopf and O3+ for facials.",
                    "Q: Do you have women stylists? A: Yes, we have women stylists for all women's services.",
                    "Q: Payment? A: UPI, cards and cash.",
                    "Q: Do you do home service? A: Only for bridal bookings.",
                ]
            ),
            "booking_instructions": "Collect: name, service(s), preferred date and time, and stylist preference if any. Repeat back and say the salon will confirm on WhatsApp.",
            "rules": "Never promise exact results for colour or keratin (depends on hair type). No skin or scalp medical advice. Hand over for: bridal and group packages, allergic reactions, complaints, refund requests.",
            "handoff_contact": "Salon manager: +91 98410 22334",
            "tone": "Friendly, upbeat and stylish. One emoji is fine.",
        },
    },
    "bakery_sweets": {
        "sample_business": "Sri Lakshmi Sweets & Bakery (Madurai)",
        "knowledge": {
            "address": "Sri Lakshmi Sweets & Bakery, 112 West Masi Street, Madurai 625001 (near Meenakshi Amman Temple West Tower).",
            "timings": "All days: 7:00 AM – 10:30 PM. Festival days: 6:00 AM – 11:00 PM.",
            "services": "\n".join(
                [
                    "Madurai special jigarthanda (glass): ₹60",
                    "Mysore pak: ₹640 per kg",
                    "Ghee laddu: ₹560 per kg",
                    "Kaju katli: ₹1,100 per kg",
                    "Mixture / karasev: ₹320 per kg",
                    "Black forest cake: ₹650 per kg",
                    "Butterscotch cake: ₹600 per kg",
                    "Photo cake: from ₹1,100 per kg",
                    "Eggless cakes: add ₹100 per kg",
                    "Veg puff: ₹25 | Paneer puff: ₹40",
                    "Sweet gift box (500 g assorted): ₹450",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Do you deliver? A: Yes, within 6 km of the shop. Delivery charge ₹40 (free above ₹1,000).",
                    "Q: How early should I order a cake? A: At least 1 day before. Photo and designer cakes need 2 days.",
                    "Q: Do you have eggless cakes? A: Yes, all cakes can be made eggless for ₹100 extra per kg.",
                    "Q: Is advance required? A: 50% advance by UPI to confirm cake and bulk orders.",
                    "Q: Do you use pure ghee? A: Yes, our ghee sweets use pure cow ghee.",
                ]
            ),
            "booking_instructions": "For cakes collect: name, cake type/flavour, weight in kg, eggless or not, message on cake, pickup or delivery (with area), date and time. For sweets collect item, quantity and date. Repeat back and say the shop will confirm and share the UPI details for advance.",
            "rules": "Never promise same-day custom cakes. Never quote bulk or wedding prices. Hand over for: orders above 5 kg, wedding/corporate orders, complaints about quality, delivery outside 6 km.",
            "handoff_contact": "Shop counter: +91 94430 55667",
            "tone": "Warm and homely, like a friendly shopkeeper. Tamil phrases welcome.",
        },
    },
    "coaching_centre": {
        "sample_business": "Bright Minds Academy (Coimbatore)",
        "knowledge": {
            "address": "Bright Minds Academy, 3rd Floor, 88 DB Road, RS Puram, Coimbatore 641002.",
            "timings": "Office: Mon–Sat 9:00 AM – 7:00 PM. Batches: weekday evenings 5–7 PM, weekend mornings 9 AM – 1 PM.",
            "services": "\n".join(
                [
                    "Class 10 Maths & Science (CBSE/State Board): ₹3,000 per month",
                    "Class 11–12 Physics, Chemistry, Maths: ₹4,500 per month",
                    "NEET long-term (1 year): ₹85,000 per year",
                    "JEE Main foundation (1 year): ₹90,000 per year",
                    "Crash course (NEET/JEE, 45 days): ₹18,000",
                    "Spoken English (2 months): ₹6,000",
                    "Registration fee (one time): ₹1,000",
                    "Free demo class: ₹0",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Is there a demo class? A: Yes, one free demo class for every course.",
                    "Q: Batch size? A: Maximum 25 students per batch.",
                    "Q: Do you give study material? A: Yes, printed material and weekly tests are included in the fee.",
                    "Q: Can fees be paid in instalments? A: Yes, yearly courses can be paid in 3 instalments.",
                    "Q: Are online classes available? A: Recorded backup of every class is shared in our app.",
                ]
            ),
            "booking_instructions": "For a demo or admission enquiry collect: student name, class/standard, board, course interested in, and preferred batch timing. Repeat back and say the counsellor will confirm on WhatsApp.",
            "rules": "Never promise ranks, marks, selections or guaranteed results. Never criticise other institutes. Hand over for: scholarship or fee discount requests, refund questions, complaints, parent meeting requests.",
            "handoff_contact": "Counsellor: +91 90030 44556",
            "tone": "Encouraging and clear. Speak respectfully to parents.",
        },
    },
    "gym": {
        "sample_business": "IronFit Gym (Tambaram, Chennai)",
        "knowledge": {
            "address": "IronFit Gym, 1st Floor, 27 GST Road, Tambaram West, Chennai 600045 (near Tambaram railway station).",
            "timings": "Mon–Sat: 5:00 AM – 10:30 PM. Sunday: 6:00 AM – 12:00 PM.",
            "services": "\n".join(
                [
                    "Monthly membership: ₹1,500",
                    "Quarterly membership (3 months): ₹4,000",
                    "Half-yearly membership (6 months): ₹7,000",
                    "Annual membership: ₹12,000",
                    "Personal training (12 sessions): ₹6,000",
                    "Zumba / HIIT group class add-on: ₹800 per month",
                    "Admission fee (one time): ₹500",
                    "Free trial session: ₹0 (one day)",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Is there a ladies batch? A: Yes, ladies-only hours 10 AM – 12 PM daily with a woman trainer.",
                    "Q: Do you have AC? A: Yes, the gym floor is fully air-conditioned.",
                    "Q: Is parking available? A: Two-wheeler parking only.",
                    "Q: Can I freeze my membership? A: Annual members can freeze for up to 30 days.",
                    "Q: Do you give diet plans? A: A basic diet chart is included with personal training.",
                ]
            ),
            "booking_instructions": "For a free trial or joining collect: name, age, fitness goal, preferred time (morning/evening). Repeat back and say the trainer will confirm on WhatsApp.",
            "rules": "Never give medical advice or supplement/steroid suggestions. Never promise weight loss numbers. Hand over for: injuries or health conditions, corporate or family packages, refund or freeze requests, complaints.",
            "handoff_contact": "Gym manager: +91 97890 11223",
            "tone": "Energetic and motivating, but short. One emoji allowed.",
        },
    },
    "real_estate": {
        "sample_business": "Homely Realty (OMR, Chennai)",
        "knowledge": {
            "address": "Homely Realty, Office 204, Rajiv Gandhi Salai (OMR), Thoraipakkam, Chennai 600097.",
            "timings": "All days: 9:30 AM – 7:30 PM. Site visits by appointment, including Sundays.",
            "services": "\n".join(
                [
                    "2 BHK apartments, Sholinganallur (1,050–1,150 sq ft): from ₹72 lakh",
                    "3 BHK apartments, Thoraipakkam (1,450–1,600 sq ft): from ₹1.15 crore",
                    "Villa plots, Kelambakkam (DTCP approved, 1,200 sq ft+): from ₹4,200 per sq ft",
                    "Rental – 2 BHK semi-furnished, Perungudi: from ₹28,000 per month",
                    "Home loan assistance: free service",
                    "Brokerage for rentals: one month's rent",
                ]
            ),
            "faqs": "\n".join(
                [
                    "Q: Are the projects RERA approved? A: Yes, all listed apartment projects are TN RERA registered. We share the number at the site visit.",
                    "Q: Can you arrange a site visit? A: Yes, with free pick-up from our OMR office.",
                    "Q: Do you help with home loans? A: Yes, we work with leading banks and help with paperwork for free.",
                    "Q: Are prices negotiable? A: Final pricing is discussed with our sales manager.",
                ]
            ),
            "booking_instructions": "For a site visit collect: name, budget, BHK/plot requirement, preferred area, and preferred date/time for the visit. Repeat back and say the sales manager will confirm on WhatsApp.",
            "rules": "Never promise returns, appreciation or rental yield. Never quote a final negotiated price or discount. No legal opinions on documents. Hand over for: price negotiation, legal/document questions, NRI purchases, complaints.",
            "handoff_contact": "Sales manager: +91 99620 33445",
            "tone": "Professional, trustworthy and helpful.",
        },
    },
}

GENERIC_TEMPLATE = {
    "sample_business": "Your Business (City)",
    "knowledge": {
        "address": "Shop/office address with a landmark.",
        "timings": "Mon–Sat: 10:00 AM – 8:00 PM. Sunday: closed.",
        "services": "Service or product 1: ₹0\nService or product 2: from ₹0",
        "faqs": "Q: Do you accept UPI? A: Yes, UPI, cards and cash.\nQ: Is parking available? A: ...",
        "booking_instructions": "Collect: name, what they need, preferred date and time. Repeat back and say the team will confirm on WhatsApp.",
        "rules": "Never promise discounts or results. Hand over for: complaints, bulk orders, anything not listed.",
        "handoff_contact": "Owner/manager phone number",
        "tone": "Warm, polite and short.",
    },
}


def template_for(niche: str) -> dict:
    tpl = TEMPLATES.get(niche, GENERIC_TEMPLATE)
    return {
        "niche": niche,
        "sample_business": tpl["sample_business"],
        "label": SAMPLE_LABEL,
        "knowledge": dict(tpl["knowledge"]),
    }
