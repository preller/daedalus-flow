"""reduce_flights: flight_collector fixture; sums part.json counts keyed by each payload's flight field; see tests/fixtures/README.md."""

import json

import numpy as np

import daedalus.flow as dae


@dae.entry
def reduce_flights(ctx: dae.FlowContext) -> None:
    # Collect (flight, count) pairs from every flight input, keyed by payload.
    pairs = []
    for flight_dir in ctx.flight_inputs.values():
        payload = json.loads((flight_dir / "part.json").read_text())
        pairs.append((payload["flight"], payload["count"]))

    # Sort by flight key for stable, order-independent output.
    pairs.sort(key=lambda pair: pair[0])
    per_flight = {flight: count for flight, count in pairs}

    # Exact integer sum (int cast keeps numpy out of the JSON).
    total_count = int(np.sum([count for _, count in pairs]))
    n_flights = len(pairs)

    reduced = {
        "per_flight": per_flight,
        "total_count": total_count,
        "n_flights": n_flights,
    }
    (ctx.step_output_path / "reduced.json").write_text(json.dumps(reduced, indent=2))
