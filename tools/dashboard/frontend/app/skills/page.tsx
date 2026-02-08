'use client';

import { useEffect, useState, useMemo } from 'react';
import {
  Sparkles,
  Search,
  ExternalLink,
  FolderOpen,
  Circle,
  ChevronDown,
  ChevronUp,
  FileText,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from '@/components/crystal';
import { api, Skill, SkillDetail } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsDir, setSkillsDir] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetail>>({});
  const [loadingDetails, setLoadingDetails] = useState<string | null>(null);

  const fetchSkills = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getSkills();
      if (res.success && res.data) {
        setSkills(res.data.skills);
        setSkillsDir(res.data.skills_dir);
      } else {
        setError(res.error || 'Failed to load skills');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load skills');
    }
    setIsLoading(false);
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const filteredSkills = useMemo(() => {
    if (!searchQuery.trim()) return skills;
    const query = searchQuery.toLowerCase();
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(query) ||
        skill.display_name.toLowerCase().includes(query) ||
        skill.description?.toLowerCase().includes(query)
    );
  }, [skills, searchQuery]);

  const handleExpandSkill = async (skillName: string) => {
    if (expandedSkill === skillName) {
      setExpandedSkill(null);
      return;
    }

    setExpandedSkill(skillName);

    // Fetch details if not cached
    if (!skillDetails[skillName]) {
      setLoadingDetails(skillName);
      try {
        const res = await api.getSkill(skillName);
        if (res.success && res.data) {
          setSkillDetails((prev) => ({ ...prev, [skillName]: res.data! }));
        }
      } catch (e) {
        console.error('Failed to fetch skill details:', e);
      }
      setLoadingDetails(null);
    }
  };

  const activeCount = skills.filter((s) => s.status === 'running').length;

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-light tracking-wide text-white/90">Skills</h1>
          <p className="text-sm text-white/40 mt-1 tracking-wide">
            Manage Claude Code skills
          </p>
        </div>
        <button
          onClick={fetchSkills}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-xl transition-all',
            'bg-white/[0.04] border border-white/[0.06]',
            'hover:bg-white/[0.08] hover:border-white/[0.10]',
            'text-sm text-white/60 hover:text-white/80'
          )}
        >
          <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-white/[0.04]">
              <Sparkles className="w-5 h-5 text-white/40" />
            </div>
            <div>
              <div className="text-2xl font-light text-white/90">{skills.length}</div>
              <div className="text-xs text-white/40">Total Skills</div>
            </div>
          </div>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <Circle className="w-5 h-5 text-emerald-400 fill-emerald-400" />
            </div>
            <div>
              <div className="text-2xl font-light text-white/90">{activeCount}</div>
              <div className="text-xs text-white/40">Currently Active</div>
            </div>
          </div>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-white/[0.04]">
              <FolderOpen className="w-5 h-5 text-white/40" />
            </div>
            <div>
              <div className="text-sm font-medium text-white/70 truncate max-w-[180px]">
                {skillsDir || '~/.claude/skills'}
              </div>
              <div className="text-xs text-white/40">Skills Directory</div>
            </div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/30" />
        <input
          type="text"
          placeholder="Search skills..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className={cn(
            'w-full pl-12 pr-4 py-3 rounded-xl',
            'bg-white/[0.02] border border-white/[0.06]',
            'text-white/90 placeholder:text-white/30',
            'focus:outline-none focus:border-white/[0.12] focus:bg-white/[0.04]',
            'transition-all'
          )}
        />
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
          <p className="text-red-400">{error}</p>
          <button
            onClick={fetchSkills}
            className="mt-2 text-sm text-white/40 hover:text-white/60 transition-colors"
          >
            Try again
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-32 rounded-xl bg-white/[0.02] border border-white/[0.04] animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && skills.length === 0 && (
        <CrystalCard className="text-center py-12">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-white/[0.04] flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-white/20" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-white/80">No Skills Installed</h3>
              <p className="text-sm text-white/40 mt-1 max-w-md">
                Skills extend Claude Code with specialized capabilities. Add skills to{' '}
                <code className="px-1.5 py-0.5 bg-white/[0.06] rounded text-white/60">
                  ~/.claude/skills/
                </code>
              </p>
            </div>
            <a
              href="https://docs.anthropic.com/claude-code/skills"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                'flex items-center gap-2 px-4 py-2 mt-2 rounded-xl transition-all',
                'bg-white/[0.04] border border-white/[0.06]',
                'hover:bg-white/[0.08] text-sm text-white/60 hover:text-white/80'
              )}
            >
              <ExternalLink className="w-4 h-4" />
              Learn about skills
            </a>
          </div>
        </CrystalCard>
      )}

      {/* Skills Grid */}
      {!isLoading && !error && filteredSkills.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              isExpanded={expandedSkill === skill.name}
              isLoadingDetails={loadingDetails === skill.name}
              details={skillDetails[skill.name]}
              onToggle={() => handleExpandSkill(skill.name)}
            />
          ))}
        </div>
      )}

      {/* No Results */}
      {!isLoading && !error && skills.length > 0 && filteredSkills.length === 0 && (
        <div className="text-center py-8">
          <p className="text-white/40">No skills match "{searchQuery}"</p>
        </div>
      )}
    </div>
  );
}

interface SkillCardProps {
  skill: Skill;
  isExpanded: boolean;
  isLoadingDetails: boolean;
  details?: SkillDetail;
  onToggle: () => void;
}

function SkillCard({
  skill,
  isExpanded,
  isLoadingDetails,
  details,
  onToggle,
}: SkillCardProps) {
  const isRunning = skill.status === 'running';

  return (
    <div
      className={cn(
        'rounded-xl transition-all duration-300 overflow-hidden',
        'bg-white/[0.02] border',
        isExpanded ? 'border-white/[0.10]' : 'border-white/[0.06]',
        'hover:border-white/[0.10]'
      )}
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full p-5 flex items-start gap-4 text-left"
      >
        {/* Status indicator */}
        <div className="relative mt-1 flex-shrink-0">
          <Circle
            className={cn(
              'w-3 h-3',
              isRunning ? 'text-emerald-400 fill-emerald-400' : 'text-white/30 fill-white/30'
            )}
          />
          {isRunning && (
            <Circle className="absolute inset-0 w-3 h-3 text-emerald-400 fill-emerald-400 animate-ping" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-medium text-white/90">{skill.display_name}</h3>
            {skill.has_instructions && (
              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-white/[0.06] text-white/40">
                Instructions
              </span>
            )}
          </div>
          {skill.description && (
            <p className="text-sm text-white/50 mt-1 line-clamp-2">{skill.description}</p>
          )}
          <div className="flex items-center gap-3 mt-2 text-xs text-white/30">
            <span className="flex items-center gap-1">
              <FolderOpen className="w-3 h-3" />
              {skill.name}
            </span>
            <span
              className={cn(
                'capitalize',
                isRunning ? 'text-emerald-400' : 'text-white/30'
              )}
            >
              {skill.status}
            </span>
          </div>
        </div>

        {/* Expand icon */}
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-white/40" />
          ) : (
            <ChevronDown className="w-5 h-5 text-white/40" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-5 pb-5 pt-0 border-t border-white/[0.04]">
          {isLoadingDetails ? (
            <div className="py-4 flex items-center justify-center">
              <RefreshCw className="w-5 h-5 text-white/40 animate-spin" />
            </div>
          ) : details ? (
            <div className="space-y-4 pt-4">
              {/* Instructions */}
              {details.instructions && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-white/40" />
                    <span className="text-xs font-medium text-white/60 uppercase tracking-wider">
                      Instructions
                    </span>
                  </div>
                  <pre className="text-xs text-white/50 bg-white/[0.02] rounded-lg p-3 overflow-x-auto max-h-48 overflow-y-auto">
                    {details.instructions}
                  </pre>
                </div>
              )}

              {/* Readme */}
              {details.readme && !details.instructions && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-white/40" />
                    <span className="text-xs font-medium text-white/60 uppercase tracking-wider">
                      README
                    </span>
                  </div>
                  <pre className="text-xs text-white/50 bg-white/[0.02] rounded-lg p-3 overflow-x-auto max-h-48 overflow-y-auto">
                    {details.readme}
                  </pre>
                </div>
              )}

              {/* No content */}
              {!details.instructions && !details.readme && (
                <p className="text-sm text-white/40 py-2">
                  No instructions or readme available.
                </p>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-2">
                <button
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all',
                    'bg-white/[0.04] border border-white/[0.06]',
                    'hover:bg-white/[0.08] text-xs text-white/60 hover:text-white/80'
                  )}
                >
                  <Terminal className="w-3.5 h-3.5" />
                  Open in Terminal
                </button>
                <button
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all',
                    'bg-white/[0.04] border border-white/[0.06]',
                    'hover:bg-white/[0.08] text-xs text-white/60 hover:text-white/80'
                  )}
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  View Files
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-white/40 py-4">Failed to load details.</p>
          )}
        </div>
      )}
    </div>
  );
}
