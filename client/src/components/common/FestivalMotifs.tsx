import React from 'react';

interface FestivalMotifsProps {
  showDandiya?: boolean;
}

export const FestivalMotifs: React.FC<FestivalMotifsProps> = ({ showDandiya = true }) => (
  <div className="festival-motifs" aria-hidden="true">
    <span className="festival-lantern festival-lantern-left" />
    <span className="festival-lantern festival-lantern-right" />
    {showDandiya && <span className="festival-dandiya" />}
    <span className="festival-rosette" />
  </div>
);
