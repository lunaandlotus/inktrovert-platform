"""Seed Issue #1 — the launch issue. Free/public teaser issue.

Real, original editorial content: evergreen guides and honest introductions
written for the launch. This issue is NOT paywalled — it's the hook that
pulls readers in and converts them to subscribers for future issues.
"""

from app.db import session_scope
from app.models import Issue, Story, utcnow


AUTHOR = "Angie Valentin"

# (slug, title, category, excerpt, paragraphs, image)
ARTICLES = [
    (
        "editors-letter-why-inktrovert",
        "A Letter From the Editor: Why Inktrovert Exists",
        "editorial",
        "I started this magazine because the industry deserved better than rumor and gatekeeping.",
        [
            "I'm Angie. I run a tattoo and piercing studio in Casper, Wyoming, and I've spent years watching this industry run on word of mouth, closed doors, and whoever shouts loudest on social media.",
            "Collectors deserve honest information. What's the difference between good work and bad work? How do you know if a shop is clean? What should aftercare actually look like? These shouldn't be mysteries you solve by getting burned first.",
            "Professionals deserve better too. A place where the craft is taken seriously. Where technique, safety, and business get the same respect as the art itself. Where apprentices can learn without being hazed and veterans can share what they know without giving away their livelihood.",
            "That's what Inktrovert is. One magazine for both sides of the chair. No gatekeeping, no fluff, no pretending. Just the real work, the real knowledge, and the real people.",
            "This first issue is free. Read it, share it, and if it speaks to you, subscribe — because there's a lot more coming.",
        ],
        "img/story-portrait.jpg",
    ),
    (
        "tattoo-aftercare-real-guide",
        "Tattoo Aftercare: What Actually Helps Ink Heal",
        "guides",
        "Wash, moisturize, protect. The fundamentals that never change.",
        [
            "Your tattoo is an open wound. Treat it like one. The first 2-4 weeks determine how your ink looks for the rest of your life, and the rules are simpler than the internet makes them seem.",
            "Keep the initial wrap on as long as your artist tells you — usually a few hours for plastic wrap, or several days for second-skin bandages like Saniderm. Don't improvise here. Your artist chose that method for a reason.",
            "Once the wrap comes off, wash gently with lukewarm water and a mild, fragrance-free soap. Pat dry with a clean towel — never rub. Then apply a thin layer of aftercare balm or fragrance-free lotion. Thin is the key word. You're moisturizing, not frosting a cake.",
            "Repeat the wash-and-moisturize routine 2-3 times a day. Wear loose clothing over the area. Stay out of pools, hot tubs, lakes, and oceans until it's fully healed. And keep it out of direct sun — UV is the enemy of fresh ink and the slow enemy of healed ink.",
            "It will itch. It will peel. That's normal. Don't scratch, don't pick at the flakes. If something looks wrong — spreading redness, heat, pus, fever — call your artist first, then a doctor if it doesn't improve. Infections are rare with proper care, but they're not something to tough out.",
            "Your artist's aftercare sheet is the final word. They know their work, their ink, and your skin. When in doubt, ask them — not a forum.",
        ],
        "img/story-aftercare.jpg",
    ),
    (
        "piercing-aftercare-real-guide",
        "Piercing Aftercare: The Patient Person's Guide",
        "guides",
        "Piercings heal on their own schedule. Your job is to not get in the way.",
        [
            "Here's what nobody tells you upfront: piercings take months to heal. Earlobes, 6-8 weeks. Cartilage, 6-12 months. Nostrils, 4-6 months. Navels, 6-12 months. Anyone who tells you otherwise is selling something.",
            "The routine is boring, and that's the point. Spray with sterile saline wound wash twice a day. That's it. Don't twist the jewelry. Don't take it out to clean it. Don't apply alcohol, hydrogen peroxide, or homemade salt mixes — they irritate the tissue you're trying to heal.",
            "Leave it alone. I know it's hard. The single biggest cause of piercing problems is hands. Every time you touch it, you introduce bacteria and disrupt the healing tissue. Look with your eyes, not your fingers.",
            "Downsizing matters. For most piercings, your piercer starts you with longer jewelry to accommodate swelling. Come back in 4-8 weeks to switch to a shorter post. Jewelry that's too long catches, snags, and migrates — downsizing isn't optional.",
            "Watch for the difference between irritation and infection. Irritation — redness, a small bump, some crusting — is common and usually resolves when you stop messing with it. Infection — spreading redness, heat, throbbing pain, fever — needs medical attention. Don't remove the jewelry if you suspect infection; that can trap it. See your piercer or a doctor.",
            "Be patient. The piercing you baby for six months will outlast the one you rushed every time.",
        ],
        "img/story-piercing.jpg",
    ),
    (
        "how-to-choose-your-artist",
        "How to Choose Your Artist (Without Getting Burned)",
        "guides",
        "Portfolios don't lie. Prices sometimes do. Here's how to read both.",
        [
            "Start with healed work. Every artist posts fresh tattoos — they're at their brightest and sharpest on day one. What matters is how the work looks at six months, a year, five years. Ask to see healed photos. A good artist has them and is proud to show them.",
            "Match the style to the artist. Don't ask a blackwork specialist for watercolor. Don't ask a fine-line artist for bold traditional. Look at what they do every day, not what they did once for a friend. You want the thing they're known for.",
            "Read the room. Is the shop clean? Do they open sterile needles in front of you? Do they wear gloves and change them? These aren't bonus points — they're the baseline. If anything feels off, walk out. There are other shops.",
            "Have a real consultation. A good artist asks questions: placement, size, your ideas, your concerns. They'll tell you when something won't work — too small, wrong placement, won't age well. An artist who says yes to everything is telling you what you want to hear, not what you need to know.",
            "Price is information. Suspiciously cheap usually means corners are being cut — on ink, on sterilization, on experience. That doesn't mean the most expensive artist is the best, but quality work costs what it costs. This is permanent. Budget accordingly.",
            "Trust your gut. You'll spend hours with this person while they put needles in your skin. You should feel comfortable, respected, and heard. If you don't, keep looking.",
        ],
        "img/story-healed.jpg",
    ),
    (
        "studio-spotlight-luna-lotus",
        "Studio Spotlight: Luna & Lotus Piercing & Ink",
        "spotlight",
        "A Casper, Wyoming shop built on referrals, honest consults, and follow-through.",
        [
            "Luna & Lotus sits inside Wind Blown Beauty Salon & Spa at 1925 Oxford Lane in Casper, Wyoming. It's owner-operated by Angie Valentin — tattoo artist, piercer, and the editor of the magazine you're reading.",
            "The shop runs Tuesday through Thursday: Tue 3-6, Wed 12:30-3:30, Thu 3-6. Walk-ins are welcome; appointments come first. It's a small operation by design — every client gets real attention, not a conveyor belt.",
            "Tattoos are custom work at $175 an hour with a $50 deposit. The age floor is 15 — never under, no exceptions. Piercings start at $45, with pricing by placement and age requirements that follow Wyoming law and basic common sense.",
            "What makes it different isn't a gimmick. It's clean work, honest consultations, and actually following up with clients. The kind of shop where people come back and bring their friends. That's the whole business model, and it works.",
            "This is the first featured studio on Inktrovert. More are coming — shops that earn it the same way: by doing the work right.",
        ],
        "img/story-studio-detail.jpg",
    ),
    (
        "apprenticeship-what-it-takes",
        "Apprenticeship: What It Actually Takes",
        "professionals",
        "Nobody hands you a machine. Here's the real path from interested to professional.",
        [
            "Every working tattoo artist started as an apprentice. There's no shortcut, no online certification, no weekend course that replaces it. An apprenticeship is typically 1-3 years of learning under an experienced mentor — and earning that mentorship is the first test.",
            "You don't find apprenticeships by asking 'are you hiring apprentices?' You find them by being around. Get tattooed. Be a good client. Show up, be respectful, draw constantly. Mentors take on people they've watched over time, not strangers who walk in with a portfolio of anime screenshots.",
            "Draw every day. Not tattoos — draw. Anatomy, still life, composition, line weight. Your portfolio should show that you understand art fundamentals, not that you can trace flash. Mentors want to see potential and work ethic, not finished tattoo designs.",
            "Expect to earn nothing for a while. Apprentices traditionally don't get paid — you're receiving an education worth tens of thousands of dollars. You'll clean, set up, break down, watch, and learn. You'll do hundreds of hours of theory before you touch skin. That's normal. That's the deal.",
            "When you do start tattooing, it'll be on fake skin, then fruit, then willing friends, then real clients under supervision. Rushing this stage is how bad tattoos happen. A good mentor won't let you skip steps, and you shouldn't want to.",
            "The apprenticeship doesn't end when you get your own station. The learning never stops — new techniques, better equipment, deeper understanding of skin. The best artists in the industry still consider themselves students.",
        ],
        "img/story-ink-bottles.jpg",
    ),
    (
        "sterile-technique-clients-guide",
        "Sterile Technique: What Every Client Should Look For",
        "guides",
        "You don't need to be a professional to spot a safe shop. Here's what to watch.",
        [
            "You have every right to watch your artist set up. In fact, you should. A professional expects it and won't be annoyed. Here's what's supposed to happen.",
            "New needles, opened in front of you. Every time, no exceptions. Needles come in sterile blister packs with expiration dates. If the pack is already open when you sit down, ask why. The answer should be 'I just opened it' — and you should have seen it.",
            "Barrier protection everywhere. The machine, the clip cord, the spray bottles, the armrest — everything that gets touched during your tattoo should be wrapped in disposable plastic. Your artist puts on fresh gloves after setup, not before handling non-sterile surfaces.",
            "Single-use ink caps. Ink should be poured into small disposable caps, never dipped from the bottle. Anything that touches your skin or the needle gets thrown away after your session. Bottles, machines, and furniture get barriers — not disinfectant spray and hope.",
            "Sharps go in a sharps container. Used needles go directly into a red puncture-proof container, not the regular trash. If you see needles sitting on a tray or going into a regular bin, that's a red flag the size of a billboard.",
            "The shop should smell like a medical office, not an art studio. Clean floors, clean bathroom, no clutter around the workstation. Sterility is a system, not a vibe — and the system is visible if you know what to look for.",
            "Now you do.",
        ],
        "img/story-needles.jpg",
    ),
    (
        "flash-vs-custom",
        "Flash vs. Custom: What's Right for You",
        "guides",
        "Neither is better. They're different tools for different jobs.",
        [
            "Flash is pre-drawn designs, displayed on the wall or in books. You pick one, the artist tattoos it. Custom is designed for you — your idea, your placement, your body. Both are legitimate. The question is what you want.",
            "Choose flash when you love a specific design as-is, want something smaller or simpler, or are working with a tighter budget. Flash days and conventions are great for this — good work, fair prices, no design back-and-forth. Some of the best tattoos in the world started as flash.",
            "Choose custom when the piece is personal, large, or needs to fit your body specifically. Portraits, memorials, sleeves, cover-ups — these need an artist thinking about your anatomy, your skin tone, and how the piece ages. That's custom territory.",
            "Custom costs more and takes longer. There's a consultation, design time, revisions, and then the session. You're paying for the artist's brain, not just their hands. Respect that process — don't ask for custom work at flash prices.",
            "A good shop does both well. Don't let anyone shame you for picking flash, and don't let anyone rush you into custom when flash would do. It's your skin. The right choice is the one you'll still love in twenty years.",
        ],
        "img/story-flash.jpg",
    ),
    (
        "the-consultation",
        "The Consultation: How to Talk to Your Artist",
        "guides",
        "Bring references, bring questions, and leave room for expertise.",
        [
            "The consultation is where good tattoos are born. It's a conversation, not an order. Here's how to make it count.",
            "Bring references — plural. Not one Pinterest image you want copied exactly, but a collection that shows the vibe: styles you like, elements you want, the feeling you're going for. More references give your artist more to work with, not less.",
            "Know your non-negotiables and be flexible on the rest. 'I want a moth, about this big, on my forearm, and it needs to incorporate my grandmother's birth flower' is a great brief. 'I want exactly this image, exactly this size, exactly here, don't change anything' is a photocopy order — and most good artists will push back on it.",
            "Listen when they push back. If your artist says the design won't work at that size, or that placement will blur in five years, or that the style doesn't suit the subject — they're not being difficult. They're using years of experience to save you from a tattoo you'll regret. This is what you're paying for.",
            "Ask about the process: how many sessions, how long each, total cost estimate, deposit terms, what happens if you need to reschedule. Get it clear upfront. Surprises about money kill more tattoo relationships than bad linework.",
            "Be honest about your pain tolerance, your medical history, and your budget. Your artist isn't judging you — they need the information to do their job safely and well.",
            "Then trust them. You chose this artist for a reason. Let them do what they do.",
        ],
        "img/story-convention.jpg",
    ),
    (
        "piercing-jewelry-materials",
        "Piercing Jewelry: What Your Skin Wants",
        "guides",
        "Not all metal is equal. Here's what belongs in a fresh piercing.",
        [
            "The jewelry in your fresh piercing matters as much as the technique. Your body is trying to heal around a foreign object — the material of that object can help or hinder the process.",
            "Implant-grade titanium (ASTM F-136) is the gold standard. It's biocompatible, nickel-free, lightweight, and comes in a range of colors through anodizing. If your piercer recommends titanium for a fresh piercing, they're giving you good advice.",
            "Implant-grade stainless steel (ASTM F-138) is also solid for fresh piercings. Niobium is another safe choice. Solid 14k or 18k gold — nickel-free, not plated — works for many people once healed, and for fresh piercings if it's from a reputable manufacturer.",
            "What's not fine for fresh piercings: plated jewelry (the plating wears off and exposes mystery metal underneath), 'surgical steel' with no grade specification (it's a marketing term, not a standard), sterling silver (tarnishes and can permanently stain skin), and anything from a mall kiosk.",
            "Threadless and internally threaded jewelry are the professional standards. The threads don't drag through the piercing channel. Externally threaded jewelry — the kind with threads on the post itself — is outdated and irritating. If your piercer is still using it, ask why.",
            "Size matters too. The gauge and length should suit the anatomy and the swelling phase. Too thin migrates. Too short embeds. Your piercer should measure, not guess.",
            "Good jewelry costs more upfront and saves you months of healing problems. It's the cheapest insurance in the piercing world.",
        ],
        "img/story-piercing-tools.jpg",
    ),
]

ISSUE = {
    "number": 1,
    "title": "Launch Issue",
    "slug": "issue-1-launch",
    "blurb": "The first issue. Real guides, honest advice, and the story of why this magazine exists — free for everyone.",
    "cover_image": "img/issue-1-cover.jpg",
}


def _seed():
    with session_scope() as db:
        # Remove the old placeholder Issue #1 if it somehow exists
        old = db.query(Issue).filter_by(slug="issue-1-launch").one_or_none()
        if old:
            db.query(Story).filter_by(issue_id=old.id).delete()
            db.delete(old)
            db.flush()

        issue = Issue(
            number=ISSUE["number"],
            title=ISSUE["title"],
            slug=ISSUE["slug"],
            blurb=ISSUE["blurb"],
            cover_image=ISSUE["cover_image"],
            is_published=True,
            is_free=True,  # Launch issue: public teaser, not paywalled
            published_at=utcnow(),
        )
        db.add(issue)
        db.flush()

        for i, (slug, title, category, excerpt, paras, image) in enumerate(ARTICLES):
            body = "".join(f"<p>{p}</p>" for p in paras)
            db.add(Story(
                issue_id=issue.id,
                title=title,
                slug=slug,
                category=category,
                excerpt=excerpt,
                body=body,
                cover_image=image,
                author_name=AUTHOR,
                sort_order=i,
                is_published=True,
                published_at=utcnow(),
            ))
        print(f"Issue #1 seed done: {len(ARTICLES)} articles.")


if __name__ == "__main__":
    _seed()
