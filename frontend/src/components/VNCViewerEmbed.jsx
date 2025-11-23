import { useEffect, useRef, useState } from 'react';

/**
 * VNC Viewer component that embeds a live desktop stream
 * 
 * The CUA VNC URL is already a noVNC web interface, so we can embed it directly.
 * To bypass CORS issues, we need to:
 * 1. Use sandbox attribute with proper permissions
 * 2. Set up proper iframe attributes for cross-origin content
 */
const VNCViewerEmbed = ({ agentId, vncUrl }) => {
  const iframeRef = useRef(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    // Reset state when URL changes
    setIsLoading(true);
    setHasError(false);
    setRetryCount(0);

    // Set a timeout to stop loading spinner if iframe doesn't respond
    const loadTimeout = setTimeout(() => {
      setIsLoading(false);
    }, 5000);

    return () => clearTimeout(loadTimeout);
  }, [vncUrl]);

  const handleLoad = () => {
    console.log(`[${agentId}] VNC viewer loaded successfully`);
    setIsLoading(false);
    setHasError(false);
  };

  const handleError = (e) => {
    console.error(`[${agentId}] VNC viewer failed to load:`, e);
    setIsLoading(false);
    setHasError(true);
  };

  const handleRetry = () => {
    setRetryCount(prev => prev + 1);
    setIsLoading(true);
    setHasError(false);
    
    // Force iframe reload by adding a cache-busting parameter
    if (iframeRef.current) {
      const url = new URL(vncUrl);
      url.searchParams.set('_retry', retryCount.toString());
      iframeRef.current.src = url.toString();
    }
  };

  const handleOpenExternal = () => {
    window.open(vncUrl, `${agentId}-vnc`, 'width=1280,height=800,menubar=no,toolbar=no,location=no,status=no');
  };

  return (
    <div className="vnc-embed">
      {isLoading && (
        <div className="vnc-embed__loading">
          <div className="vnc-embed__spinner"></div>
          <span>Connecting to {agentId} desktop...</span>
          <small>This may take a few seconds</small>
        </div>
      )}
      
      {hasError && (
        <div className="vnc-embed__error">
          <div className="vnc-embed__error-icon">⚠️</div>
          <h3>Connection Issue</h3>
          <p>Unable to embed {agentId} desktop stream</p>
          <div className="vnc-embed__error-actions">
            <button onClick={handleRetry} className="vnc-embed__btn vnc-embed__btn--retry">
              🔄 Retry Connection
            </button>
            <button onClick={handleOpenExternal} className="vnc-embed__btn vnc-embed__btn--external">
              🔗 Open in New Window
            </button>
          </div>
          <small className="vnc-embed__error-hint">
            Tip: Opening in a new window usually works better
          </small>
        </div>
      )}
      
      <iframe
        ref={iframeRef}
        src={vncUrl}
        title={`${agentId} VNC Desktop Stream`}
        className="vnc-embed__iframe"
        onLoad={handleLoad}
        onError={handleError}
        // Sandbox permissions for cross-origin iframe
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-pointer-lock"
        // Allow fullscreen
        allow="fullscreen; clipboard-read; clipboard-write"
        // Security attributes
        referrerPolicy="no-referrer"
        loading="lazy"
        style={{ 
          display: (isLoading || hasError) ? 'none' : 'block',
          opacity: isLoading ? 0 : 1,
          transition: 'opacity 0.3s ease-in-out'
        }}
      />
      
      {/* Fallback overlay when iframe is loading */}
      {!hasError && !isLoading && (
        <div className="vnc-embed__overlay">
          <button 
            onClick={handleOpenExternal}
            className="vnc-embed__fullscreen-btn"
            title="Open in new window for better experience"
          >
            🔗 Open Fullscreen
          </button>
        </div>
      )}
    </div>
  );
};

export default VNCViewerEmbed;

