from __future__ import annotations

import pytest

from services.meal import normalize_meal_components
from services.vision import (
    FoodCandidate,
    FoodComponent,
    HiddenIngredientRisk,
    PortionEstimate,
    StateHint,
    StructuredFoodComponent,
    VisionAnalysisResponse,
)


def test_normalize_meal_components_legacy_input_normalizes_text_and_builds_trace() -> None:
    normalized = normalize_meal_components(
        [
            FoodComponent(
                name="  White   Rice  ",
                confidence=0.91,
                portion_hint=" 100   g ",
            )
        ]
    )

    assert normalized.meal_uncertainty_flags == ()
    assert len(normalized.components) == 1

    component = normalized.components[0]
    assert component.component_id == "legacy_component_1"
    assert component.name == "white rice"
    assert component.confidence == pytest.approx(0.91)
    assert component.portion_hint == "100 g"
    assert component.source_component_ids == ("legacy_component_1",)
    assert component.source_component_names == ("White Rice",)
    assert len(component.top_food_candidates) == 1
    assert component.top_food_candidates[0].name == "white rice"
    assert component.top_food_candidates[0].confidence == pytest.approx(0.91)
    assert component.top_food_candidates[0].visual_evidence == ()


def test_normalize_meal_components_structured_input_normalizes_and_carries_uncertainty() -> None:
    response = VisionAnalysisResponse(
        meal_uncertainty_flags=["  Low   Light ", "low light", "  Occluded  plate "],
        components=[
            StructuredFoodComponent(
                component_id="  comp-01 ",
                visible_name="  Grilled   Chicken  ",
                candidates=[
                    FoodCandidate(
                        name="  Grilled   Chicken Breast ",
                        confidence=0.88,
                        visual_evidence=["  char   marks ", "char marks", "brown edge"],
                    ),
                    FoodCandidate(
                        name="  Chicken  Thigh ",
                        confidence=0.57,
                        visual_evidence=[" darker meat "],
                    ),
                ],
                portion=PortionEstimate(
                    description="  about   1 palm ",
                    confidence=0.76,
                    visual_basis=["plate scale"],
                ),
                state_hints=[
                    StateHint(
                        state="grilled",
                        confidence=0.80,
                        visual_evidence=["  seared lines ", "seared lines"],
                    )
                ],
                hidden_ingredient_risks=[
                    HiddenIngredientRisk(
                        ingredient="  oil  ",
                        likelihood=0.44,
                        macro_impact="medium",
                        rationale=" shiny surface ",
                    )
                ],
            )
        ],
    )

    normalized = normalize_meal_components(response)

    assert normalized.meal_uncertainty_flags == ("low light", "occluded plate")
    assert len(normalized.components) == 1

    component = normalized.components[0]
    assert component.component_id == "comp-01"
    assert component.name == "grilled chicken breast"
    assert component.source_component_ids == ("comp-01",)
    assert component.source_component_names == ("Grilled Chicken",)
    assert component.portion_hint == "about 1 palm"

    assert len(component.state_hints) == 1
    assert component.state_hints[0].state == "grilled"
    assert component.state_hints[0].confidence == pytest.approx(0.80)
    assert component.state_hints[0].visual_evidence == ("seared lines",)

    assert len(component.hidden_ingredient_risks) == 1
    assert component.hidden_ingredient_risks[0].ingredient == "oil"
    assert component.hidden_ingredient_risks[0].likelihood == pytest.approx(0.44)
    assert component.hidden_ingredient_risks[0].macro_impact == "medium"
    assert component.hidden_ingredient_risks[0].rationales == ("shiny surface",)


def test_normalize_meal_components_merges_duplicate_components_with_source_traces() -> None:
    normalized = normalize_meal_components(
        [
            FoodComponent(name="  WHITE   RICE ", confidence=0.62, portion_hint="half cup"),
            FoodComponent(name="white rice", confidence=0.90, portion_hint="100 g"),
        ]
    )

    assert len(normalized.components) == 1
    component = normalized.components[0]

    assert component.component_id == "legacy_component_1"
    assert component.name == "white rice"
    assert component.confidence == pytest.approx(0.90)
    assert component.portion_hint == "100 g"
    assert component.source_component_ids == ("legacy_component_1", "legacy_component_2")
    assert component.source_component_names == ("WHITE RICE", "white rice")

    assert len(component.top_food_candidates) == 1
    assert component.top_food_candidates[0].name == "white rice"
    assert component.top_food_candidates[0].confidence == pytest.approx(0.90)


def test_normalize_meal_components_preserves_top_k_candidates_and_visual_evidence() -> None:
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="salad-1",
                visible_name="salad",
                candidates=[
                    FoodCandidate(
                        name=" Caesar   salad ",
                        confidence=0.74,
                        visual_evidence=["romaine leaves", " creamy dressing "],
                    ),
                    FoodCandidate(
                        name=" garden salad ",
                        confidence=0.66,
                        visual_evidence=["tomato", " cucumber "],
                    ),
                    FoodCandidate(
                        name=" coleslaw ",
                        confidence=0.41,
                        visual_evidence=["shredded cabbage"],
                    ),
                ],
                portion=PortionEstimate(
                    description="1 bowl",
                    confidence=0.60,
                    visual_basis=["bowl diameter"],
                ),
            )
        ]
    )

    normalized = normalize_meal_components(response)
    component = normalized.components[0]

    assert [candidate.name for candidate in component.top_food_candidates] == [
        "caesar salad",
        "garden salad",
        "coleslaw",
    ]
    assert component.top_food_candidates[0].visual_evidence == (
        "romaine leaves",
        "creamy dressing",
    )
    assert component.top_food_candidates[1].visual_evidence == ("tomato", "cucumber")
    assert component.top_food_candidates[2].visual_evidence == ("shredded cabbage",)


def test_normalize_meal_components_preserves_hidden_risk_flags_after_duplicate_merge() -> None:
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="fries-a",
                visible_name=" fries ",
                candidates=[
                    FoodCandidate(
                        name="french fries",
                        confidence=0.81,
                        visual_evidence=["golden strips"],
                    )
                ],
                portion=PortionEstimate(
                    description="1 serving",
                    confidence=0.55,
                    visual_basis=["hand scale"],
                ),
                hidden_ingredient_risks=[
                    HiddenIngredientRisk(
                        ingredient="oil",
                        likelihood=0.61,
                        macro_impact="high",
                        rationale="deep-fried texture",
                    ),
                    HiddenIngredientRisk(
                        ingredient="salt",
                        likelihood=0.50,
                        macro_impact="low",
                        rationale="visible crystals",
                    ),
                ],
            ),
            StructuredFoodComponent(
                component_id="fries-b",
                visible_name=" Fries ",
                candidates=[
                    FoodCandidate(
                        name=" french fries ",
                        confidence=0.86,
                        visual_evidence=["golden strips", "oil sheen"],
                    )
                ],
                portion=PortionEstimate(
                    description="large side",
                    confidence=0.72,
                    visual_basis=["plate coverage"],
                ),
                hidden_ingredient_risks=[
                    HiddenIngredientRisk(
                        ingredient=" oil ",
                        likelihood=0.83,
                        macro_impact="high",
                        rationale="glossy surface",
                    )
                ],
            ),
        ]
    )

    normalized = normalize_meal_components(response)
    assert len(normalized.components) == 1

    risks = normalized.components[0].hidden_ingredient_risks
    assert len(risks) == 2
    assert risks[0].ingredient == "oil"
    assert risks[0].macro_impact == "high"
    assert risks[0].likelihood == pytest.approx(0.83)
    assert risks[0].rationales == ("deep-fried texture", "glossy surface")
    assert risks[1].ingredient == "salt"
    assert risks[1].macro_impact == "low"
    assert risks[1].likelihood == pytest.approx(0.50)
    assert risks[1].rationales == ("visible crystals",)


def test_normalize_meal_components_preserves_state_hints_after_duplicate_merge() -> None:
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="tofu-a",
                visible_name=" tofu ",
                candidates=[
                    FoodCandidate(
                        name="fried tofu",
                        confidence=0.62,
                        visual_evidence=["crispy edge"],
                    )
                ],
                portion=PortionEstimate(
                    description="small block",
                    confidence=0.51,
                    visual_basis=["fork scale"],
                ),
                state_hints=[
                    StateHint(
                        state="fried",
                        confidence=0.41,
                        visual_evidence=["golden crust"],
                    )
                ],
            ),
            StructuredFoodComponent(
                component_id="tofu-b",
                visible_name="Tofu",
                candidates=[
                    FoodCandidate(
                        name=" fried tofu ",
                        confidence=0.78,
                        visual_evidence=["browned side"],
                    )
                ],
                portion=PortionEstimate(
                    description="small block",
                    confidence=0.68,
                    visual_basis=["plate scale"],
                ),
                state_hints=[
                    StateHint(
                        state="fried",
                        confidence=0.76,
                        visual_evidence=["oil sheen"],
                    ),
                    StateHint(
                        state="sauced",
                        confidence=0.55,
                        visual_evidence=["glaze"],
                    ),
                ],
            ),
        ]
    )

    normalized = normalize_meal_components(response)
    assert len(normalized.components) == 1

    hints = normalized.components[0].state_hints
    assert len(hints) == 2
    assert hints[0].state == "fried"
    assert hints[0].confidence == pytest.approx(0.76)
    assert hints[0].visual_evidence == ("golden crust", "oil sheen")
    assert hints[1].state == "sauced"
    assert hints[1].confidence == pytest.approx(0.55)
    assert hints[1].visual_evidence == ("glaze",)
