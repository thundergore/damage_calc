import streamlit as st
from damage_calc import WeaponProfile, expected_damage_total, Effects

st.set_page_config(page_title="AoS Average Damage Calculator", page_icon="⚡", layout="wide")
st.title("Age of Sigmar — Average Damage Calculator (Effects-enabled)")
st.caption("Hit → Wound → Save (Rend & mods) → Ward → Damage | Re-rolls, 6s, explosions, mortals")

with st.sidebar:
    st.header("Defender")
    target_save = st.number_input("Save (e.g., 4 for 4+)", min_value=2, max_value=6, value=4, step=1)
    defender_save_mod = st.number_input("Save modifier on defender", min_value=-3, max_value=3, value=0, step=1)
    has_ward = st.checkbox("Ward?", value=False)
    target_ward = st.number_input("Ward (e.g., 6 for 6+)", min_value=2, max_value=6, value=6, step=1) if has_ward else None

st.subheader("Weapon Profiles")
default_rows = st.number_input("How many profiles?", min_value=1, max_value=20, value=2, step=1)

profiles = []
for i in range(default_rows):
    with st.expander(f"Profile {i+1}", expanded=(i < 2)):
        name = st.text_input("Name", value=f"Weapon {i+1}", key=f"name{i}")
        attacks = st.number_input("Attacks", min_value=0, max_value=200, value=4, step=1, key=f"att{i}")
        c1, c2, c3 = st.columns(3)
        with c1:
            hit = st.number_input("To Hit (+)", min_value=2, max_value=6, value=3, step=1, key=f"hit{i}")
            hit_mod = st.number_input("Hit mod (±)", min_value=-3, max_value=3, value=0, step=1, key=f"hmod{i}")
        with c2:
            wound = st.number_input("To Wound (+)", min_value=2, max_value=6, value=3, step=1, key=f"w{i}")
            wound_mod = st.number_input("Wound mod (±)", min_value=-3, max_value=3, value=0, step=1, key=f"wmod{i}")
        with c3:
            rend = st.number_input("Rend (e.g., -2)", min_value=-6, max_value=0, value=-1, step=1, key=f"rend{i}")
            damage = st.text_input("Damage (2, D3, D6, 2D3+1)", value="2", key=f"dam{i}")

        st.markdown("**Effects**")
        e1, e2, e3 = st.columns(3)
        with e1:
            reroll_hit = st.selectbox("Re-roll hit", options=["none","ones","failed"], index=0, key=f"rrh{i}")
            explode = st.number_input("Explode on 6 to hit (+hits)", min_value=0, max_value=5, value=0, step=1, key=f"exp{i}")
        with e2:
            reroll_wound = st.selectbox("Re-roll wound", options=["none","ones","failed"], index=0, key=f"rrw{i}")
            autowound6 = st.checkbox("Auto-wound on 6 to hit", value=False, key=f"aw6{i}")
        with e3:
            m_hit_val = st.text_input("Mortals on 6 to hit (e.g., D3 / blank)", value="", key=f"mhv{i}")
            m_hit_mode = st.selectbox("Hit mortals mode", options=["instead","in_addition"], index=0, key=f"mhm{i}")
            cont_after_hit = st.checkbox("Continue to wound after hit-mortals", value=False, key=f"cont{i}")

        f1, f2 = st.columns(2)
        with f1:
            m_wnd_val = st.text_input("Mortals on 6 to wound (e.g., 1 / blank)", value="", key=f"mwv{i}")
            m_wnd_mode = st.selectbox("Wound mortals mode", options=["instead","in_addition"], index=0, key=f"mwm{i}")
        with f2:
            explode_auto_applies = st.checkbox("Explosions also apply to auto-wounds", value=True, key=f"exauto{i}")

        effects = Effects(
            reroll_hit=reroll_hit,
            reroll_wound=reroll_wound,
            explode_on_hit_6=explode,
            autowound_on_hit_6=autowound6,
            mortal_on_hit_6_value=(m_hit_val if m_hit_val.strip() else None),
            mortal_on_hit_6_mode=m_hit_mode,
            continue_to_wound_after_mortal_on_hit=cont_after_hit,
            mortal_on_wound_6_value=(m_wnd_val if m_wnd_val.strip() else None),
            mortal_on_wound_6_mode=m_wnd_mode,
            explode_applies_to_autowounds=explode_auto_applies,
        )

        profiles.append(
            WeaponProfile(
                name=name, attacks=attacks, hit=hit, wound=wound, rend=rend, damage=damage,
                hit_mod=hit_mod, wound_mod=wound_mod,
                target_save=target_save, defender_save_mod=defender_save_mod, target_ward=target_ward,
                effects=effects
            )
        )

st.divider()

rows = []
total = 0.0
for p in profiles:
    ed = p.expected_damage()
    total += ed
    rows.append(
        {
            "Profile": p.name,
            "Attacks": p.attacks,
            "Hit+": f"{p.hit} ({'+' if p.hit_mod>=0 else ''}{p.hit_mod})",
            "Wound+": f"{p.wound} ({'+' if p.wound_mod>=0 else ''}{p.wound_mod})",
            "Rend": p.rend,
            "Damage": p.damage,
            "Exp. Damage": round(ed, 3),
        }
    )

st.subheader("Results")
st.dataframe(rows, use_container_width=True)
st.metric("Total Expected Damage", round(total, 3))
st.info(
    "Assumptions: 6s are natural; mortals bypass normal save but can be warded; "
    "explosions add *hits*, not extra rolls; auto-wounds skip wound roll. "
    "Re-roll 'failed' = optimal (reroll only failures)."
)
