import { useState } from 'react';

const VNCViewer = ({ agentId, vncUrl }) => {
  const [isHovered, setIsHovered] = useState(false);

  const handleOpenVNC = () => {
    window.open(vncUrl, `${agentId}-vnc`, 'width=1200,height=800,menubar=no,toolbar=no,location=no');
  };

  return (
    <div 
      className="vnc-viewer vnc-viewer--clickable"
      onClick={handleOpenVNC}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="vnc-viewer__placeholder">
        <div className="vnc-viewer__icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
            <line x1="8" y1="21" x2="16" y2="21"/>
            <line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
        </div>
        <div className="vnc-viewer__text">
          <h3>{isHovered ? '🖱️ Click to open' : '🖥️ Live Desktop'}</h3>
          <p>{agentId} VNC viewer</p>
        </div>
        {isHovered && (
          <div className="vnc-viewer__badge">
            Open in new window →
          </div>
        )}
      </div>
    </div>
  );
};

export default VNCViewer;

