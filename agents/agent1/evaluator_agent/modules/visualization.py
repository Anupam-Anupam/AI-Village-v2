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
    
    for idx, (agent_id, snapshots) in enumerate(agent_snapshots.items()):
        if not snapshots:
            continue
        
        # Sort snapshots by timestamp
        sorted_snapshots = sorted(
            snapshots,
            key=lambda x: x.get("collected_at") or x.get("timestamp") or ""
        )
        
        # Deduplicate snapshots - keep only unique progress values
        # This reduces noise from frequent logging at the same progress level
        unique_snapshots = []
        last_progress = None
        for snapshot in sorted_snapshots:
            current_progress = snapshot.get("progress_percent", 0.0)
            if last_progress is None or abs(current_progress - last_progress) >= 0.1:
                unique_snapshots.append(snapshot)
                last_progress = current_progress
        
        sorted_snapshots = unique_snapshots
        
        if not sorted_snapshots:
            continue
        
        # Always start from origin (0%, step 0)
        first_snapshot = sorted_snapshots[0]
        if first_snapshot.get("progress_percent", 0) > 0:
            origin_snapshot = {
                "agent_id": agent_id,
                "progress_percent": 0.0,
                "step": 0,
                "collected_at": first_snapshot.get("collected_at"),
                "timestamp": first_snapshot.get("timestamp")
            }
            sorted_snapshots.insert(0, origin_snapshot)
        
        # Extract data using normalized step indices
        timestamps = []
        progress_values = []
        normalized_steps = []
        
        for snap_idx, snapshot in enumerate(sorted_snapshots):
            timestamp = snapshot.get("collected_at") or snapshot.get("timestamp")
            progress = snapshot.get("progress_percent", 0.0)
            
            # Use normalized step index (0, 1, 2, 3...) for clean visualization
            normalized_step = snap_idx
            
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
            
            normalized_steps.append(normalized_step)
        
        # Create hover text with original step info if available
        hover_text = []
        for snap_idx, (norm_step, progress, ts, snapshot) in enumerate(zip(normalized_steps, progress_values, timestamps, sorted_snapshots)):
            original_step = snapshot.get("step", norm_step)
            hover_text.append(
                f"Agent: {agent_id}<br>"
                f"Snapshot: {norm_step}<br>"
                f"Original Step: {original_step}<br>"
                f"Progress: {progress:.1f}%<br>"
                f"Time: {str(ts)}"
            )
        
        color = colors[idx % len(colors)]
        
        # Add trace for this agent with smooth curves
        fig.add_trace(go.Scatter(
            x=normalized_steps,
            y=progress_values,
            mode="lines+markers",
            name=agent_id,
            text=hover_text,
            hoverinfo="text",
            line=dict(color=color, width=2, shape='spline'),  # Smooth curve
            marker=dict(size=3, line=dict(width=0.5, color='DarkSlateGrey'))
        ))
    
    fig.update_layout(
        title="Agent Progress Comparison",
        xaxis_title="Snapshot Index",
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
        xaxis=dict(
            tickmode='linear',
            tick0=0,
            dtick=5
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
