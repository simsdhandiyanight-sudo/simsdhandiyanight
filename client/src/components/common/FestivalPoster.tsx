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
        src="/dhandiya-night-festival-celebration.png"
        alt="Dhandiya Night festival celebration at Soundarya Institute"
        className={`festival-poster__image ${imageClassName}`}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
      />
    </div>
  </figure>
);
