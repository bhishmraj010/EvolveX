"""
Builds the data the 'Your Growth Roadmap' mastery-curve chart needs:
a smooth SVG path through each phase's checkpoint, plus pixel coordinates
for the checkpoint dots/label-cards and the x/y axis labels — mirrors the
reference EvolveX design (mastery % on Y, time on X, dashed goal marker).
"""
from datetime import timedelta


VIEW_W = 1200
VIEW_H = 300
PAD_L = 46   # room for Y axis %
PAD_R = 90   # room for the GOAL trophy node
PAD_T = 26
PAD_B = 34   # room for X axis month labels

INNER_W = VIEW_W - PAD_L - PAD_R
INNER_H = VIEW_H - PAD_T - PAD_B


def _catmull_rom_to_bezier_path(points):
    """points: list[(x, y)] -> smooth SVG path 'd' string (cubic beziers)."""
    if len(points) < 2:
        return ""
    if len(points) == 2:
        (x0, y0), (x1, y1) = points
        return f"M {x0:.2f},{y0:.2f} L {x1:.2f},{y1:.2f}"

    d = f"M {points[0][0]:.2f},{points[0][1]:.2f} "
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2

        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6

        d += f"C {c1x:.2f},{c1y:.2f} {c2x:.2f},{c2y:.2f} {p2[0]:.2f},{p2[1]:.2f} "
    return d.strip()


def _fmt_month(d):
    return d.strftime("%b '%y")


def build_growth_chart(roadmap, phases):
    """Returns None if there isn't enough data yet (no phases)."""
    if not phases:
        return None

    total = len(phases)
    start_date = roadmap.created_at.date() if hasattr(roadmap.created_at, "date") else roadmap.created_at
    end_date = roadmap.target_deadline or roadmap.predicted_completion_date

    total_duration_days = sum(p.duration_days for p in phases) or 1
    if end_date and end_date > start_date:
        span_days = (end_date - start_date).days
    else:
        span_days = int(total_duration_days * 1.15)  # leave headroom for the GOAL node
    span_days = max(span_days, total_duration_days + 1)

    # denom = total + 1 so the *last real checkpoint* lands just under 100%,
    # leaving the final stretch of curve for the standalone GOAL node.
    denom = total + 1

    raw_points = [(0.0, 100.0)]  # start: 0% mastery, top-left of inner chart (y=100 -> bottom)
    node_meta = []
    cum_days = 0
    for i, phase in enumerate(phases):
        cum_days += phase.duration_days
        x_pct = min(92.0, round(cum_days / span_days * 100, 1))
        mastery_pct = round((i + 1) / denom * 100)
        y_pct = 100 - mastery_pct  # SVG y grows downward
        raw_points.append((x_pct, y_pct))

        checkpoint = getattr(phase, "checkpoint", None)
        node_date = phase.completed_at.date() if phase.completed_at else (start_date + timedelta(days=cum_days))
        node_meta.append({
            "index": i,
            "x_pct": x_pct,
            "y_pct": y_pct,
            "mastery_pct": mastery_pct,
            "phase": phase,
            "checkpoint": checkpoint,
            "date": node_date,
            "status": phase.status,
            "label_below": (i + 1) % 5 == 0,  # matches reference: checkpoint 5 sits below the line
        })

    # Final standalone GOAL node
    goal_date = end_date or (start_date + timedelta(days=span_days))
    raw_points.append((100.0, 0.0))

    # convert % -> SVG viewBox coordinates
    def to_xy(pct_pair):
        px, py = pct_pair
        x = PAD_L + (px / 100) * INNER_W
        y = PAD_T + (py / 100) * INNER_H
        return (x, y)

    svg_points = [to_xy(p) for p in raw_points]
    path_d = _catmull_rom_to_bezier_path(svg_points)

    nodes = []
    for m in node_meta:
        x, y = to_xy((m["x_pct"], m["y_pct"]))
        left_pct = round(x / VIEW_W * 100, 2)
        if m["label_below"]:
            top_pct = round((y + 14) / VIEW_H * 100, 2)
        else:
            top_pct = round(max(0, y - 92) / VIEW_H * 100, 2)
        nodes.append({
            **m, "svg_x": round(x, 1), "svg_y": round(y, 1),
            "left_pct": left_pct, "top_pct": top_pct,
        })

    goal_x, goal_y = svg_points[-1]
    goal_left_pct = round(goal_x / VIEW_W * 100, 2)
    goal_top_pct = round(max(0, goal_y - 78) / VIEW_H * 100, 2)

    # X axis month labels — 6 evenly spaced points from start_date to goal_date
    x_labels = []
    steps = 6
    for s in range(steps + 1):
        frac = s / steps
        d = start_date + timedelta(days=round(span_days * frac))
        x_labels.append({"left_pct": round(frac * INNER_W / VIEW_W * 100 + PAD_L / VIEW_W * 100, 2), "label": _fmt_month(d)})

    y_labels = [
        {"y": round(PAD_T + INNER_H * (1 - v / 100), 1), "label": f"{v}%"}
        for v in (0, 25, 50, 75, 100)
    ]

    return {
        "view_w": VIEW_W,
        "view_h": VIEW_H,
        "pad_l": PAD_L,
        "pad_t": PAD_T,
        "axis_bottom_y": VIEW_H - PAD_B,
        "inner_w": INNER_W,
        "inner_h": INNER_H,
        "path_d": path_d,
        "nodes": nodes,
        "goal_x": round(goal_x, 1),
        "goal_y": round(goal_y, 1),
        "goal_left_pct": goal_left_pct,
        "goal_top_pct": goal_top_pct,
        "goal_date": goal_date,
        "x_labels": x_labels,
        "y_labels": y_labels,
    }