# Cross-Cultural Fixture Set

This fixture family checks that component normalization and source matching do
not collapse culturally specific foods into misleading generic categories.

Minimum locale groups:

- `zh`: congee with century egg, mapo tofu with rice, hotpot plate with dipping sauce;
- `vi`: pho bo, banh mi, bun thit nuong with nuoc cham;
- `th`: pad kra pao with rice, green curry, som tam;
- `ja`: salmon sushi set, ramen with egg, curry rice;
- `ko`: bibimbap, kimchi jjigae, kimbap;
- `hi/ur`: chicken biryani, dal with rice, chana masala with roti.

Each fixture should include:

- fixture id;
- locale tag;
- image or text input reference;
- expected visible components;
- ambiguous aliases or romanizations;
- hidden ingredient risks;
- expected source family preferences;
- notes on portion and sauce uncertainty.

Fixtures must not contain raw personal user images unless explicit consent was
granted and privacy review removed unrelated personal details. Public or
synthetic examples should be preferred during v0.3.
