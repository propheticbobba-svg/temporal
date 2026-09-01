from datetime import UTC, datetime

from backend.brief import (
    Brief,
    BriefModule,
    CategoryBrief,
    GraphBeat,
    GraphBridge,
    GraphEdge,
    GraphEntity,
    GraphFusion,
    GraphGap,
    GraphPlan,
    GraphThought,
    GraphTrailFusion,
    PlaceGraph,
    SignalRead,
    SourceNote,
    candidate_anomalies,
)
from backend.think import ground_fusion, worth_fusing


def test_ground_fusion_keeps_only_known_ids() -> None:
    brief = _brief()
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="A licensed cafe is on file at this address.",
            model="deepseek-ai/deepseek-v3.2-maas",
            trails=[
                GraphTrailFusion(
                    module_id="business_activity",
                    headline="Cafe Luna is the licensed operator.",
                    beats=[
                        GraphBeat(
                            edge_id="operated-0",
                            when="2026",
                            line="Cafe Luna holds a retail food license.",
                        ),
                        GraphBeat(
                            edge_id="invented",
                            when="2020",
                            line="A tenant named Pat lived here.",
                        ),
                    ],
                ),
                GraphTrailFusion(
                    module_id="occupancy",
                    headline="Someone lived here.",
                    beats=[],
                ),
            ],
        ),
    )

    assert fused.place_read.startswith("A licensed cafe")
    assert [trail.module_id for trail in fused.trails] == ["business_activity"]
    assert [beat.edge_id for beat in fused.trails[0].beats] == ["operated-0"]
    assert fused.sources[0].edge_id == "operated-0"
    assert fused.sources[0].when == "2026"


def test_ground_fusion_keeps_only_known_plan_ids() -> None:
    fused = ground_fusion(
        _brief(),
        GraphFusion(
            place_read="On file.",
            trails=[],
            plan=GraphPlan(
                expand=["business_activity", "occupancy"],
                tight=["tenancy"],
                lead="ghost",
            ),
        ),
    )
    assert fused.plan is not None
    assert fused.plan.expand == ["business_activity"]
    assert fused.plan.tight == []
    assert fused.plan.lead is None


def test_ground_fusion_keeps_one_note_per_origin() -> None:
    fused = ground_fusion(
        _brief(),
        GraphFusion(
            place_read="On file.",
            sources_read="Chicago licenses name the operator.",
            sources=[
                SourceNote(
                    origin="Chicago business licenses",
                    proved="Cafe Luna is licensed.",
                    when="2026-01-15T00:00:00",
                    edge_id="operated-0",
                ),
                SourceNote(
                    origin="Chicago business licenses",
                    proved="A second copy of the same register.",
                    when="2020",
                    edge_id="operated-0",
                ),
            ],
        ),
    )
    assert [note.origin for note in fused.sources] == ["Chicago business licenses"]
    assert fused.sources[0].when == "2026"
    assert fused.sources_read.startswith("Chicago licenses")


def test_ground_fusion_keeps_gaps_only_for_open_trails() -> None:
    brief = _brief()
    brief.modules.append(
        BriefModule(
            id="inspections",
            title="Inspections",
            question="Inspections?",
            trail="Inspections.",
            status="uncovered",
            summary="No inspection feed is wired for this place yet.",
        )
    )
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            gaps=[
                GraphGap(
                    module_id="inspections",
                    why="No health inspection portal is live for this city.",
                ),
                GraphGap(module_id="business_activity", why="Invented gap on an answered trail."),
                GraphGap(module_id="ghost", why="Unknown trail."),
            ],
        ),
    )
    assert [gap.module_id for gap in fused.gaps] == ["inspections"]
    assert "health inspection" in fused.gaps[0].why


def test_ground_fusion_keeps_only_sourced_bridges() -> None:
    brief = _brief()
    brief.graph.entities.append(
        GraphEntity(id="entity:REROOF", kind="work", label="Reroof P-1", key="REROOF P 1")
    )
    brief.graph.entities.append(
        GraphEntity(id="entity:JOE", kind="contractor", label="Joe", key="JOE")
    )
    brief.graph.edges.append(
        GraphEdge(
            id="serviced-work-0",
            rel="SERVICED",
            from_id="entity:JOE",
            entity_id="entity:REROOF",
            capability="site_work",
            source="permits",
            observed_at=datetime(2026, 2, 1, tzinfo=UTC),
            summary="Joe serviced the reroof.",
            confidence=0.9,
        )
    )
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            bridges=[
                GraphBridge(
                    from_id="entity:JOE",
                    to_id="entity:REROOF",
                    why="Permit names Joe as the contractor on this work.",
                    confidence=0.9,
                    edge_ids=["serviced-work-0"],
                ),
                GraphBridge(
                    from_id="entity:CAFE LUNA",
                    to_id="entity:JOE",
                    why="Guessed they are related.",
                    confidence=0.4,
                    edge_ids=["operated-0", "serviced-work-0"],
                ),
            ],
        ),
    )
    assert [bridge.to_id for bridge in fused.bridges] == ["entity:REROOF"]


def test_ground_fusion_keeps_grounded_thoughts() -> None:
    brief = _brief()
    brief.graph.entities.append(
        GraphEntity(id="entity:REROOF", kind="work", label="Reroof P-1", key="REROOF P 1")
    )
    brief.graph.entities.append(
        GraphEntity(id="entity:JOE", kind="contractor", label="Joe", key="JOE")
    )
    brief.graph.edges.append(
        GraphEdge(
            id="serviced-work-0",
            rel="SERVICED",
            from_id="entity:JOE",
            entity_id="entity:REROOF",
            capability="site_work",
            source="permits",
            observed_at=datetime(2026, 2, 1, tzinfo=UTC),
            summary="Joe serviced the reroof.",
            confidence=0.9,
        )
    )
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            thoughts=[
                GraphThought(
                    kind="link",
                    line="The permit names Joe on this reroof.",
                    from_id="entity:JOE",
                    to_id="entity:REROOF",
                    edge_ids=["serviced-work-0"],
                ),
                GraphThought(
                    kind="link",
                    line="Cafe Luna hired Joe.",
                    from_id="entity:CAFE LUNA",
                    to_id="entity:JOE",
                    edge_ids=["operated-0"],
                ),
                GraphThought(
                    kind="watch",
                    line="A secret tenant named Pat lived here.",
                    from_id="entity:ghost",
                ),
            ],
        ),
    )
    assert [(item.kind, item.from_id, item.to_id) for item in fused.thoughts] == [
        ("link", "entity:JOE", "entity:REROOF"),
    ]


def test_local_thoughts_note_when_nearby_is_not_an_occupant() -> None:
    brief = _brief()
    brief.graph.entities.append(
        GraphEntity(id="entity:BURGLARY", kind="context", label="Burglary", key="BURGLARY")
    )
    brief.graph.edges.append(
        GraphEdge(
            id="nearby-burglary-0",
            rel="NEARBY",
            entity_id="entity:BURGLARY",
            capability="neighborhood",
            source="crime_nearby",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            summary="12 burglary reports nearby.",
            confidence=0.8,
        )
    )
    fused = ground_fusion(brief, GraphFusion(place_read="On file."))
    nearby = next(item for item in fused.thoughts if "street context" in item.line)
    assert nearby.from_id == "neighborhood"
    assert nearby.also_ids == ["business_activity"]


def test_ground_fusion_builds_watch_thoughts_from_anomalies() -> None:
    brief = _flagged_brief()
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            anomalies=["Cafe Luna's retail food license expired and was not replaced."],
        ),
    )
    assert fused.thoughts
    assert fused.thoughts[0].kind == "watch"
    assert fused.thoughts[0].from_id == "entity:CAFE LUNA"
    assert "expired" in fused.thoughts[0].line.lower()


def test_ground_fusion_lets_model_veto_anomalies() -> None:
    brief = _flagged_brief()
    fused = ground_fusion(brief, GraphFusion(place_read="On file.", anomalies=[]))
    assert fused.anomalies == []
    assert fused.anomalies_judged is True


def test_ground_fusion_keeps_rewritten_candidate_anomaly() -> None:
    brief = _flagged_brief()
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            anomalies=["Cafe Luna's retail food license expired and was not replaced."],
        ),
    )
    assert fused.anomalies == ["Cafe Luna's retail food license expired and was not replaced."]
    assert fused.anomalies_judged is True


def test_ground_fusion_drops_invented_anomalies() -> None:
    brief = _flagged_brief()
    fused = ground_fusion(
        brief,
        GraphFusion(
            place_read="On file.",
            anomalies=["A secret tenant named Pat lived here."],
        ),
    )
    assert fused.anomalies == candidate_anomalies(brief)
    assert fused.anomalies_judged is True


def test_worth_fusing_skips_empty_templates() -> None:
    brief = _brief()
    brief.graph.edges.clear()
    brief.modules[0].status = "uncovered"
    assert worth_fusing(brief) is False
    brief.graph.edges.append(
        GraphEdge(
            id="operated-0",
            rel="OPERATED_AT",
            entity_id="entity:CAFE LUNA",
            capability="business_activity",
            source="biz_licenses",
            observed_at=datetime(2026, 1, 15, tzinfo=UTC),
            summary="A retail food license for Cafe Luna was issued.",
            confidence=1.0,
        )
    )
    assert worth_fusing(brief) is True


def _flagged_brief() -> Brief:
    brief = _brief()
    return brief.model_copy(
        update={
            "operational_activity": CategoryBrief(
                signals=[
                    SignalRead(
                        source="biz_licenses",
                        signal_type="anomaly",
                        observed_at=datetime(2025, 1, 1, tzinfo=UTC),
                        value={
                            "legal_name": "CAFE LUNA",
                            "license_type": "Retail Food",
                            "license_status": "EXP",
                        },
                        summary="Cafe Luna expired.",
                        is_anomaly=True,
                        confidence=1.0,
                    )
                ]
            )
        }
    )


def _brief() -> Brief:
    empty = CategoryBrief()
    return Brief(
        address="123 MAIN ST, CHICAGO, IL, 60601",
        generated_at=datetime(2026, 1, 15, tzinfo=UTC),
        narrative="Commercial.",
        place_class="commercial",
        place_class_label="Commercial",
        place_class_assumed=False,
        modules=[
            BriefModule(
                id="business_activity",
                title="Who operated here",
                question="Who operated at this site?",
                trail="Licensed businesses.",
                status="answered",
                summary="A retail food license for Cafe Luna was issued.",
            )
        ],
        graph=PlaceGraph(
            place_id="place",
            place_label="123 MAIN ST, CHICAGO, IL, 60601",
            entities=[
                GraphEntity(
                    id="entity:CAFE LUNA",
                    kind="business",
                    label="Cafe Luna",
                    key="CAFE LUNA",
                )
            ],
            edges=[
                GraphEdge(
                    id="operated-0",
                    rel="OPERATED_AT",
                    entity_id="entity:CAFE LUNA",
                    capability="business_activity",
                    source="biz_licenses",
                    observed_at=datetime(2026, 1, 15, tzinfo=UTC),
                    summary="A retail food license for Cafe Luna was issued.",
                    confidence=1.0,
                )
            ],
        ),
        physical_condition=empty,
        regulatory_standing=empty,
        operational_activity=empty,
        environmental_context=empty,
    )
