import React from 'react';

interface ConfidenceBarProps {
  value: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  variant?: 'bar' | 'ring';
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({
  value,
  size = 'md',
  showLabel = true,
  variant = 'bar',
}) => {
  const percentage = Math.round(value * 100);
  
  const getColor = (val: number): string => {
    if (val < 0.3) return 'from-rose-500 to-rose-600';
    if (val < 0.7) return 'from-amber-500 to-amber-600';
    return 'from-emerald-500 to-emerald-600';
  };

  const getTextColor = (val: number): string => {
    if (val < 0.3) return 'text-rose-400';
    if (val < 0.7) return 'text-amber-400';
    return 'text-emerald-400';
  };

  const sizeClasses = {
    sm: 'h-1.5',
    md: 'h-2.5',
    lg: 'h-3.5',
  };

  const textSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  if (variant === 'ring') {
    const circumference = 2 * Math.PI * 18;
    const offset = circumference - (value * circumference);
    const ringSize = size === 'sm' ? 40 : size === 'md' ? 48 : 56;

    return (
      <div className="relative inline-flex items-center justify-center">
        <svg width={ringSize} height={ringSize} className="transform -rotate-90">
          <circle
            cx={ringSize / 2}
            cy={ringSize / 2}
            r="18"
            className="stroke-slate-700"
            strokeWidth="4"
            fill="none"
          />
          <circle
            cx={ringSize / 2}
            cy={ringSize / 2}
            r="18"
            className={`bg-gradient-to-r ${getColor(value)}`}
            stroke="url(#gradient)"
            strokeWidth="4"
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
          <defs>
            <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" className={getColor(value).split(' ')[0].replace('from-', '')} />
              <stop offset="100%" className={getColor(value).split(' ')[1].replace('to-', '')} />
            </linearGradient>
          </defs>
        </svg>
        {showLabel && (
          <span className={`absolute ${textSizes[size]} font-semibold ${getTextColor(value)}`}>
            {percentage}%
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 bg-slate-700 rounded-full overflow-hidden ${sizeClasses[size]}`}>
        <div
          className={`h-full bg-gradient-to-r ${getColor(value)} transition-all duration-500 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <span className={`${textSizes[size]} font-semibold ${getTextColor(value)} min-w-[3rem] text-right`}>
          {percentage}%
        </span>
      )}
    </div>
  );
};
