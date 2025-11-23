import { useState, useEffect } from 'react';
import { API_BASE } from '../config';

const EvaluatorView = () => {
  const [evaluatorData, setEvaluatorData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fetchEvaluatorData = async () => {
      try {
        // Placeholder - replace with actual evaluator API endpoint when available
        const response = await fetch(`${API_BASE}/evaluator/status`);
        if (response.ok) {
          const data = await response.json();
          setEvaluatorData(data);
        }
        // Silently fail if endpoint doesn't exist yet
      } catch (err) {
        // Silently fail - evaluator endpoint not yet implemented
      } finally {
        setIsLoading(false);
      }
    };

    fetchEvaluatorData();
    const interval = setInterval(fetchEvaluatorData, 10000); // Refresh every 10s

    return () => clearInterval(interval);
  }, []);

  const status = evaluatorData?.status || 'loading';
  const stats = {
    totalEvaluations: evaluatorData?.total_evaluations || 0,
    agentsEvaluated: evaluatorData?.agents_evaluated || 0,
    tasksEvaluated: evaluatorData?.tasks_evaluated || 0,
    averageScore: evaluatorData?.average_score || 0,
  };
  const recentEvaluations = evaluatorData?.recent_evaluations || [];

  return (
    <div className="evaluator-view">
      <div className="evaluator-header">
        <h1>Evaluator Dashboard</h1>
        <p>Monitor agent performance and evaluation metrics</p>
        {status === 'running' && (
          <span style={{ 
            display: 'inline-block', 
            marginLeft: '10px',
            padding: '4px 12px',
            background: 'rgba(34, 197, 94, 0.1)',
            color: '#22c55e',
            borderRadius: '12px',
            fontSize: '0.875rem',
            fontWeight: '500'
          }}>
            ● Active
          </span>
        )}
      </div>

      <div className="evaluator-grid">
        {/* Placeholder cards for evaluator metrics */}
        <div className="evaluator-card">
          <div className="evaluator-card__header">
            <h3>📊 Evaluation Stats</h3>
          </div>
          <div className="evaluator-card__body">
            <div className="metric-row">
              <span className="metric-label">Total Evaluations</span>
              <span className="metric-value">{stats.totalEvaluations}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Agents Evaluated</span>
              <span className="metric-value">{stats.agentsEvaluated}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Tasks Evaluated</span>
              <span className="metric-value">{stats.tasksEvaluated}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Average Score</span>
              <span className="metric-value">{stats.averageScore.toFixed(1)}%</span>
            </div>
          </div>
        </div>

        <div className="evaluator-card">
          <div className="evaluator-card__header">
            <h3>🎯 Agent Scores</h3>
          </div>
          <div className="evaluator-card__body">
            <div className="agent-score">
              <span className="agent-name">🤖 Agent 1</span>
              <div className="score-bar">
                <div className="score-fill" style={{ width: '0%' }}></div>
              </div>
              <span className="score-value">—</span>
            </div>
            <div className="agent-score">
              <span className="agent-name">🦾 Agent 2</span>
              <div className="score-bar">
                <div className="score-fill" style={{ width: '0%' }}></div>
              </div>
              <span className="score-value">—</span>
            </div>
            <div className="agent-score">
              <span className="agent-name">🧠 Agent 3</span>
              <div className="score-bar">
                <div className="score-fill" style={{ width: '0%' }}></div>
              </div>
              <span className="score-value">—</span>
            </div>
          </div>
        </div>

        <div className="evaluator-card evaluator-card--wide">
          <div className="evaluator-card__header">
            <h3>📈 Recent Evaluations</h3>
          </div>
          <div className="evaluator-card__body">
            {recentEvaluations.length === 0 ? (
              <div style={{ 
                color: 'var(--muted-text)', 
                textAlign: 'center',
                padding: '40px 20px'
              }}>
                No evaluation data available yet. Evaluations will appear here once agents complete tasks.
              </div>
            ) : (
              <div className="evaluations-list">
                {recentEvaluations.map((evaluation, idx) => (
                  <div key={idx} className="evaluation-item" style={{
                    padding: '12px',
                    borderBottom: idx < recentEvaluations.length - 1 ? '1px solid rgba(255,255,255,0.1)' : 'none',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}>
                    <div>
                      <div style={{ fontWeight: '500' }}>
                        Task #{evaluation.task_id} - {evaluation.agent_id}
                      </div>
                      <div style={{ fontSize: '0.875rem', color: 'var(--muted-text)', marginTop: '4px' }}>
                        {evaluation.evaluated_at && new Date(evaluation.evaluated_at).toLocaleString()}
                      </div>
                    </div>
                    <div style={{ 
                      fontSize: '1.25rem', 
                      fontWeight: 'bold',
                      color: (evaluation.scores?.overall_score || 0) >= 70 ? '#22c55e' : '#f59e0b'
                    }}>
                      {evaluation.scores?.overall_score || 0}%
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EvaluatorView;

