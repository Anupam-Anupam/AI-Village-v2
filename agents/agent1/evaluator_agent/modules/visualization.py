import io
import json
import logging
from typing import Any, Dict, List

import plotly.graph_objects as go

logger = logging.getLogger("evaluator_agent")


def build_performance_figure(reports: List[Dict[str, Any]]) -> go.Figure:
    if not reports:
        # Return empty figure if no reports
        return go.Figure()
        
    # Sort by evaluation time if present
    def key_fn(r):
        return r.get("evaluated_at") or r.get("collected_at") or ""
    
    data = sorted(reports, key=key_fn)
    
    # Always start from origin - insert a 0 point if first score > 0
    # Use sequence numbers for x-axis to ensure all points are visible
    first_score = float(((data[0].get("scores") or {}).get("final_score") or 0.0)) if data else 0.0
    
    if first_score > 0:
        # Insert origin point
        x = [0] + list(range(1, len(data) + 1))
        y = [0.0] + [float(((r.get("scores") or {}).get("final_score") or 0.0)) for r in data]
        timestamps = ["Start"] + [r.get("evaluated_at") or r.get("collected_at") or "" for r in data]
    else:
        x = list(range(1, len(data) + 1))
        y = [float(((r.get("scores") or {}).get("final_score") or 0.0)) for r in data]
        timestamps = [r.get("evaluated_at") or r.get("collected_at") or "" for r in data]
    
    # Create hover text with both timestamp and score
    hover_text = []
    for i, (ts, score) in enumerate(zip(timestamps, y)):
        if ts == "Start":
            hover_text.append(f"Origin<br>Score: 0.00")
        else:
            hover_text.append(f"Snapshot {i}<br>Time: {ts}<br>Score: {score:.2f}")

    fig = go.Figure()
    
    # Add scatter plot with hover text
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="lines+markers",
        name="Final Score",
        text=hover_text,
        hoverinfo="text+y",
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=8, line=dict(width=1, color='DarkSlateGrey'))
    ))
    
    # Add annotations for first and last points
    if len(data) > 1:
        for idx in [0, -1]:
            fig.add_annotation(
                x=x[idx],
                y=y[idx],
                text=f"{y[idx]:.2f}",
                showarrow=True,
                arrowhead=1,
                ax=0,
                ay=-20 if idx == 0 else 20
            )
    
    fig.update_layout(
        title="Agent Performance Over Time",
        xaxis_title="Snapshot #",
        yaxis_title="Final Score",
        template="plotly_white",
        height=500,
        width=900,
        margin=dict(l=50, r=30, t=60, b=50),
        hovermode='closest',
        xaxis=dict(
            tickmode='array',
            tickvals=x,
            ticktext=[f"{i}" for i in x]
        ),
        yaxis=dict(
            rangemode='tozero'  # Ensure y-axis starts at 0
        )
    )
    return fig


def build_multi_agent_progress_figure(
    agent_snapshots: Dict[str, List[Dict[str, Any]]]
) -> go.Figure:
    """
    Build a plotly figure showing progress over time for multiple agents.
    
    Args:
        agent_snapshots: Dictionary mapping agent_id to list of progress snapshots
        
    Returns:
        Plotly figure
    """
    from datetime import datetime, timedelta
    
    fig = go.Figure()
    
    # Color palette for different agents
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    
    # First pass: check if we should use timestamps or steps across all agents
    # Collect all timestamps to check for large gaps
    all_agent_timestamp_ranges = []
    for agent_id, snapshots in agent_snapshots.items():
        if not snapshots:
            continue
        sorted_snapshots = sorted(
            snapshots,
            key=lambda x: x.get("collected_at") or x.get("timestamp") or ""
        )
        timestamps = []
        for snapshot in sorted_snapshots:
            timestamp = snapshot.get("collected_at") or snapshot.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamps.append(ts)
                except:
                    pass
        if timestamps:
            all_agent_timestamp_ranges.append((min(timestamps), max(timestamps)))
    
    # Check if there are large time gaps between agents (e.g., different days)
    # or if the time span is too large compared to individual agent spans
    use_steps_globally = False
    if len(all_agent_timestamp_ranges) > 1:
        global_min = min(r[0] for r in all_agent_timestamp_ranges)
        global_max = max(r[1] for r in all_agent_timestamp_ranges)
        total_span = (global_max - global_min).total_seconds()
        
        # Calculate average individual agent span
        avg_agent_span = sum((r[1] - r[0]).total_seconds() for r in all_agent_timestamp_ranges) / len(all_agent_timestamp_ranges)
        
        # If the total span is more than 100x the average agent span, use steps
        # This handles cases where agents ran on different days
        if total_span > avg_agent_span * 100 and avg_agent_span < 3600:  # less than 1 hour avg
            use_steps_globally = True
            logger.info(json.dumps({
                "event": "graph_x_axis_global_decision",
                "decision": "using_steps",
                "reason": "large_time_gap_between_agents",
                "total_span_seconds": total_span,
                "avg_agent_span_seconds": avg_agent_span,
                "ratio": total_span / avg_agent_span if avg_agent_span > 0 else 0
            }))
    
    for idx, (agent_id, snapshots) in enumerate(agent_snapshots.items()):
        if not snapshots:
            continue
        
        # Sort snapshots by timestamp
        sorted_snapshots = sorted(
            snapshots,
            key=lambda x: x.get("collected_at") or x.get("timestamp") or ""
        )
        
        # Always start from origin (0%, step 0)
        # Insert a starting point if the first snapshot doesn't start at 0
        first_snapshot = sorted_snapshots[0] if sorted_snapshots else None
        if first_snapshot and first_snapshot.get("progress_percent", 0) > 0:
            # Create an origin point just before the first real snapshot
            origin_snapshot = {
                "agent_id": agent_id,
                "progress_percent": 0.0,
                "step": 0,
                "collected_at": first_snapshot.get("collected_at"),
                "timestamp": first_snapshot.get("timestamp")
            }
            sorted_snapshots.insert(0, origin_snapshot)
        
        # Extract data
        timestamps = []
        progress_values = []
        steps = []
        
        for snap_idx, snapshot in enumerate(sorted_snapshots):
            timestamp = snapshot.get("collected_at") or snapshot.get("timestamp")
            progress = snapshot.get("progress_percent", 0.0)
            # Use actual step number if available, otherwise use index + 1 (since we may have added origin at 0)
            step = snapshot.get("step", snap_idx + 1)
            
            # Normalize timestamp
            if isinstance(timestamp, str):
                try:
                    from datetime import datetime
                    ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamps.append(ts)
                except:
                    timestamps.append(len(timestamps))
            else:
                timestamps.append(timestamp if timestamp else len(timestamps))
            
            # Convert progress to percentage if needed
            if isinstance(progress, (int, float)):
                if progress <= 1.0:
                    progress_values.append(progress * 100)
                else:
                    progress_values.append(min(100.0, progress))
            else:
                progress_values.append(0.0)
            
            steps.append(step)
        
        # Use step numbers for x-axis if timestamps are not available or all identical
        # or if there's a large time gap between agents
        if use_steps_globally:
            x_values = steps if steps else list(range(1, len(sorted_snapshots) + 1))
            x_label = "Step"
        elif all(isinstance(t, int) for t in timestamps):
            x_values = steps if steps else list(range(1, len(sorted_snapshots) + 1))
            x_label = "Step"
        else:
            # Check if all timestamps are the same (would cause vertical line)
            unique_timestamps = set(str(t) for t in timestamps)
            if len(unique_timestamps) <= 1 and len(timestamps) > 1:
                # All timestamps are identical, use step numbers instead
                x_values = steps if steps else list(range(1, len(sorted_snapshots) + 1))
                x_label = "Step"
                logger.warning(json.dumps({
                    "event": "graph_x_axis_all_timestamps_identical",
                    "agent_id": agent_id
                }))
            else:
                x_values = timestamps
                x_label = "Time"
        
        # Create hover text
        hover_text = [
            f"Agent: {agent_id}<br>"
            f"Step: {step}<br>"
            f"Progress: {progress:.1f}%<br>"
            f"Time: {str(ts)}"
            for step, progress, ts in zip(steps, progress_values, timestamps)
        ]
        
        color = colors[idx % len(colors)]
        
        # Add trace for this agent
        fig.add_trace(go.Scatter(
            x=x_values,
            y=progress_values,
            mode="lines+markers",
            name=agent_id,
            text=hover_text,
            hoverinfo="text+y",
            line=dict(color=color, width=2),
            marker=dict(size=8, line=dict(width=1, color='DarkSlateGrey'))
        ))
    
    fig.update_layout(
        title="Agent Progress Over Time",
        xaxis_title=x_label,
        yaxis_title="Progress (%)",
        template="plotly_white",
        height=600,
        width=1200,
        margin=dict(l=50, r=30, t=60, b=50),
        hovermode='closest',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        yaxis=dict(
            range=[0, 105],  # Start at 0, go slightly above 100 for visibility
            tickmode='linear',
            tick0=0,
            dtick=10
        )
    )
    
    return fig


def figure_to_png_bytes(fig: go.Figure) -> bytes:
    buf = io.BytesIO()
    fig.write_image(buf, format="png", engine="kaleido")
    return buf.getvalue()


def figure_to_png_file(fig: go.Figure, filepath: str) -> None:
    """Save plotly figure as PNG file to local machine."""
    fig.write_image(filepath, format="png", engine="kaleido")
