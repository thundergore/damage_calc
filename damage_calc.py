from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional, Literal

# ---------- Helpers ----------

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

def prob_success_on(target: int) -> float:
    t = clamp(target, 2, 6)
    return (7 - t) / 6.0  # P(d6 >= t)

def expected_from_dice(expr: str) -> float:
    s = expr.strip().lower().replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    s = re.sub(r"(^|[+\-])d", r"\g<1>1d", s)
    tokens = re.findall(r"[+\-]?[^+\-]+", s)
    total = 0.0
    for tok in tokens:
        sign = -1.0 if tok.startswith("-") else 1.0
        core = tok[1:] if tok[0] in "+-" else tok
        m = re.fullmatch(r"(\d+)d(3|6)(?:\*(\d+))?", core)
        if m:
            n = int(m.group(1)); sides = int(m.group(2)); mult = int(m.group(3) or 1)
            total += sign * n * ((sides + 1) / 2.0) * mult
        else:
            if not re.fullmatch(r"\d+(\.\d+)?", core):
                raise ValueError(f"Unsupported dice expression: {tok}")
            total += sign * float(core)
    return total

# ---------- Effects model ----------

RerollMode = Literal["none", "ones", "failed"]

@dataclass
class Effects:
    # Re-rolls
    reroll_hit: RerollMode = "none"
    reroll_wound: RerollMode = "none"

    # Exploding hits: on natural 6 to hit, add N extra hits
    explode_on_hit_6: int = 0  # N extra hits per natural 6

    # Auto-wound on natural 6 to hit
    autowound_on_hit_6: bool = False

    # Mortals on 6s (configurable behavior)
    # On hit
    mortal_on_hit_6_value: Optional[str] = None  # e.g., "1", "D3"
    mortal_on_hit_6_mode: Literal["instead", "in_addition"] = "instead"
    continue_to_wound_after_mortal_on_hit: bool = False  # only used if "in_addition"

    # On wound
    mortal_on_wound_6_value: Optional[str] = None
    mortal_on_wound_6_mode: Literal["instead", "in_addition"] = "instead"

    # Does exploding also apply to auto-wounds from 6s to hit?
    explode_applies_to_autowounds: bool = True

def p_success_with_reroll(p: float, mode: RerollMode) -> float:
    """Analytical P(success) after re-roll policy."""
    if mode == "none":
        return p
    if mode in ("failed",):  # optimal play: reroll only fails
        return p + (1 - p) * p  # = p*(2 - p)
    if mode == "ones":
        return p + (1/6) * p
    raise ValueError("Unknown reroll mode")

def p_nat6_with_reroll(success_p_no_mod: float, mode: RerollMode) -> float:
    """
    Probability that the *final kept roll* is a natural 6, given a policy.
    success_p_no_mod is the success prob WITHOUT reroll (used to know when reroll triggers on 'failed').
    """
    q6 = 1/6
    if mode == "none":
        return q6
    if mode == "ones":
        # first is 6 OR (first is 1 AND reroll is 6)
        return q6 + (1/6) * q6
    if mode == "failed":
        # first is 6 OR (first fails AND reroll is 6)
        return q6 + (1 - success_p_no_mod) * q6
    raise ValueError("Unknown reroll mode")

# ---------- Data model ----------

@dataclass
class WeaponProfile:
    name: str
    attacks: int
    hit: int
    wound: int
    rend: int
    damage: str

    # Offensive mods
    hit_mod: int = 0
    wound_mod: int = 0

    # Defensive context
    target_save: int = 4
    defender_save_mod: int = 0
    target_ward: Optional[int] = None

    # Effects
    effects: Effects = field(default_factory=Effects)

    # --- Expected value calculation ---
    def expected_damage(self) -> float:
        """
        Returns expected TOTAL damage (normal + mortal) per profile under these assumptions:
        - d6 system, 1s always fail, 6s can trigger effects.
        - Save is modified by rend & defender save mods; ward is unmodified.
        - Mortals ignore normal save but can be warded.
        - Explosions add *hits*; each added hit follows the same downstream logic (except it cannot retro-trigger the 'on-hit 6' of the original die).
        - 'Auto-wound on 6 to hit' converts those hits directly to wounds (skip wound roll).
        - Re-roll policies: "failed" means re-roll failed only (optimal play); "ones" re-roll only 1s.
        - Triggers are on **natural** 6s.
        """
        e = self.effects

        # --- Stage probabilities (base, no rerolls yet) ---
        hit_target   = clamp(self.hit   - self.hit_mod, 2, 6)
        wound_target = clamp(self.wound - self.wound_mod, 2, 6)
        save_target  = clamp(self.target_save - self.rend - self.defender_save_mod, 2, 6)

        p_hit_base   = prob_success_on(hit_target)
        p_wound_base = prob_success_on(wound_target)
        p_save       = prob_success_on(save_target)
        p_ward       = prob_success_on(self.target_ward) if self.target_ward else 0.0
        e_normal_dmg = expected_from_dice(self.damage)

        # --- Apply rerolls to success probabilities ---
        p_hit = p_success_with_reroll(p_hit_base, e.reroll_hit)
        p_wound = p_success_with_reroll(p_wound_base, e.reroll_wound)

        # Natural 6 trigger probabilities after reroll policy
        p_hit_nat6   = p_nat6_with_reroll(p_hit_base, e.reroll_hit)
        p_wound_nat6 = p_nat6_with_reroll(p_wound_base, e.reroll_wound)

        # --- Exploding hits on natural 6 to hit ---
        extra_hits_per_attack = e.explode_on_hit_6 * p_hit_nat6  # expected extra hits from explosions

        # --- Auto-wounds on 6 to hit ---
        p_autowound_from_hit = p_hit_nat6 if e.autowound_on_hit_6 else 0.0

        # Note: if auto-wound occurs, it *skips* wound roll. Remaining successful non-6 hits still roll to wound.
        # Expected successful non-auto-wound hits:
        # total successful hits minus autowound-converted hits (those all came from natural 6 successes; but not all 6s are successes if target is 6+? 6 always succeeds.)
        # With AoS clamp, 6 always succeeds; so autowound contributions are p_hit_nat6.
        exp_successful_hits_per_attack = p_hit
        exp_autowound_hits_per_attack  = p_autowound_from_hit
        exp_non_auto_hits_per_attack   = max(0.0, exp_successful_hits_per_attack - exp_autowound_hits_per_attack)

        # Add explosions: each explosion yields an extra hit which is *not* an auto-6; it must roll to wound normally.
        # (Most rules add one extra hit, not an extra roll; modelling as an extra hit that then wounds on wound profile is standard.)
        exp_hits_including_explosions = exp_successful_hits_per_attack + extra_hits_per_attack

        # Separate those extra hits into "need wound roll" bucket (all extra hits need wound roll)
        exp_hits_need_wound = exp_non_auto_hits_per_attack + extra_hits_per_attack
        exp_auto_wounds     = exp_autowound_hits_per_attack  # go straight to save (no wound roll)

        # --- Mortals on HIT (natural 6) ---
        e_mortal_on_hit = expected_from_dice(e.mortal_on_hit_6_value) if e.mortal_on_hit_6_value else 0.0
        exp_mortals_on_hit_raw = p_hit_nat6 * e_mortal_on_hit

        if e.mortal_on_hit_6_value and e.mortal_on_hit_6_mode == "instead":
            # Those procs replace normal effect. They should be removed from both auto-wound and wound paths.
            # Each proc consumes one hit that would have at least been a success (6 always succeeds).
            # Remove its contribution from auto-wounds (if any) AND from non-auto-hit pool.
            # Since triggers are subset of natural 6s, and all 6s counted in exp_successful_hits_per_attack,
            # we subtract from exp_auto_wounds first (if auto-wound enabled), else from hits_need_wound.
            consume = p_hit_nat6  # procs per attack
            if e.autowound_on_hit_6 and e.explode_applies_to_autowounds:
                # Subtract from autowound pool
                exp_auto_wounds = max(0.0, exp_auto_wounds - consume)
            else:
                # Subtract from the general "need wound" pool
                exp_hits_need_wound = max(0.0, exp_hits_need_wound - consume)

        # If "in addition", keep normal flow; optionally allow continuing to wound
        if e.mortal_on_hit_6_value and e.mortal_on_hit_6_mode == "in_addition" and not e.continue_to_wound_after_mortal_on_hit:
            # The attack does not continue; remove the proc count from downstream pools
            consume = p_hit_nat6
            # Prefer to reduce auto-wounds if applicable, else reduce hits_need_wound
            if e.autowound_on_hit_6 and e.explode_applies_to_autowounds:
                exp_auto_wounds = max(0.0, exp_auto_wounds - consume)
            else:
                exp_hits_need_wound = max(0.0, exp_hits_need_wound - consume)

        # --- Wound stage (for those that need it) ---
        exp_successful_wounds_from_rolls = exp_hits_need_wound * p_wound

        # --- Mortals on WOUND (natural 6) ---
        e_mortal_on_wound = expected_from_dice(e.mortal_on_wound_6_value) if e.mortal_on_wound_6_value else 0.0
        # Expected number of wound rolls made = exp_hits_need_wound (each makes one roll)
        exp_mortal_procs_on_wound = exp_hits_need_wound * p_wound_nat6
        exp_mortals_on_wound_raw  = exp_mortal_procs_on_wound * e_mortal_on_wound

        if e.mortal_on_wound_6_value and e.mortal_on_wound_6_mode == "instead":
            # Replace the normal wound for those procs: remove them from successful wounds pool.
            # Note a natural 6 is also a success, so subtract from successful wounds.
            exp_successful_wounds_from_rolls = max(0.0, exp_successful_wounds_from_rolls - exp_mortal_procs_on_wound)

        # If "in addition", keep them and also keep normal wound success.

        # --- Total wounds delivered to SAVE stage (before save) ---
        exp_wounds_before_save = exp_auto_wounds + exp_successful_wounds_from_rolls

        # --- Normal damage after save+ward ---
        p_unsaved  = (1 - p_save)
        p_unwarded = (1 - p_ward)
        exp_normal_damage_per_attack = (exp_wounds_before_save * p_unsaved * p_unwarded) * e_normal_dmg

        # --- Mortal wounds after ward only ---
        exp_mortal_wounds_per_attack = (exp_mortals_on_hit_raw + exp_mortals_on_wound_raw) * p_unwarded

        # --- Sum & scale by number of attacks ---
        total_per_attack = exp_normal_damage_per_attack + exp_mortal_wounds_per_attack
        return self.attacks * total_per_attack

# ---------- Batch utility ----------

def expected_damage_total(profiles: list[WeaponProfile]) -> float:
    return sum(p.expected_damage() for p in profiles)
