import { useEffect } from 'react';

/**
 * VNC Stream Component - Direct iframe embedding
 */
const VNCStreamMini = ({ agentId, vncUrl }) => {
  const baseUrl = vncUrl || "https://m-linux-kpzcblkosd.containers.cloud.trycua.com/vnc.html?autoconnect=true&password=4b1478417d084de2";
  
  // Append resize=scale to ensure the remote screen scales to fit the iframe
  const separator = baseUrl.includes('?') ? '&' : '?';
  const embedUrl = baseUrl.includes('resize=scale') ? baseUrl : `${baseUrl}${separator}resize=scale`;

  useEffect(() => {
    console.log(`[${agentId}] VNC URL:`, embedUrl);
  }, [embedUrl, agentId]);

  return (
    <div className="vnc-stream-mini">
      <iframe
        src={embedUrl}
        title={`${agentId} Live VNC Stream`}
        className="vnc-stream-mini__iframe"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
};

export default VNCStreamMini;

