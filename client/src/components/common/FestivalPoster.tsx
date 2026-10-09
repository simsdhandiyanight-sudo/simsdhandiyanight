import React from 'react';

interface FestivalPosterProps {
  className?: string;
  imageClassName?: string;
  priority?: boolean;
}

export const FestivalPoster: React.FC<FestivalPosterProps> = ({
  className = '',
  imageClassName = '',
  priority = false,
}) => (
  <figure className={`festival-poster ${className}`}>
    <div className="festival-poster__frame">
      <img
        src="/dandiya-night-poster.png"
        sizes="(max-width: 768px) 100vw, 940px"
        alt="Dhandiya Night 2026 event poster"
        className={`festival-poster__image ${imageClassName}`}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding={priority ? 'sync' : 'async'}
      />
    </div>
  </figure>
);
