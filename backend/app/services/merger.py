from dataclasses import dataclass, field


@dataclass
class MergedField:
    value: str | None
    confidence: float
    source_panel: str
    bounding_box: dict | None = None


@dataclass
class FieldConflict:
    field_name: str
    panels: dict[str, str]  # panel -> value
    resolved_value: str
    resolved_panel: str


@dataclass
class MergedExtraction:
    fields: dict[str, MergedField] = field(default_factory=dict)
    conflicts: list[FieldConflict] = field(default_factory=list)


# Panel priority: front > back > other
PANEL_PRIORITY = {"front": 0, "back": 1, "other": 2}


class ImageMerger:
    """Combines extraction results from multiple panels into a single field set."""

    def merge_panels(
        self, panel_results: dict[str, dict[str, dict]]
    ) -> MergedExtraction:
        merged = MergedExtraction()

        # Collect all fields across panels
        field_sources: dict[str, list[tuple[str, dict]]] = {}
        for panel, fields in panel_results.items():
            for field_name, field_data in fields.items():
                if field_name not in field_sources:
                    field_sources[field_name] = []
                field_sources[field_name].append((panel, field_data))

        for field_name, sources in field_sources.items():
            if len(sources) == 1:
                # Single source - use directly
                panel, data = sources[0]
                merged.fields[field_name] = MergedField(
                    value=data.get("value"),
                    confidence=data.get("confidence", 0.0),
                    source_panel=panel,
                    bounding_box=data.get("bounding_box"),
                )
            else:
                # Multiple sources - check for conflicts
                values = {panel: data.get("value") for panel, data in sources}
                unique_values = set(v for v in values.values() if v)

                if len(unique_values) <= 1:
                    # Same value across panels - use highest confidence
                    best = max(sources, key=lambda s: s[1].get("confidence", 0.0))
                    panel, data = best
                    merged.fields[field_name] = MergedField(
                        value=data.get("value"),
                        confidence=data.get("confidence", 0.0),
                        source_panel=panel,
                        bounding_box=data.get("bounding_box"),
                    )
                else:
                    # Conflict - prefer front panel
                    sorted_sources = sorted(
                        sources,
                        key=lambda s: PANEL_PRIORITY.get(s[0], 99),
                    )
                    best_panel, best_data = sorted_sources[0]

                    merged.fields[field_name] = MergedField(
                        value=best_data.get("value"),
                        confidence=best_data.get("confidence", 0.0),
                        source_panel=best_panel,
                        bounding_box=best_data.get("bounding_box"),
                    )

                    merged.conflicts.append(
                        FieldConflict(
                            field_name=field_name,
                            panels=values,
                            resolved_value=best_data.get("value", ""),
                            resolved_panel=best_panel,
                        )
                    )

        return merged
