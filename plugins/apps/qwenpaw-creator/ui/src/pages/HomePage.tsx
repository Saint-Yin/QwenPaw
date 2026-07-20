import { useEffect, useState, useCallback, memo } from "react";
import { Modal, message } from "antd";
import { Plus, Trash2, ExternalLink, Film, Clock3 } from "lucide-react";
import type { ProjectSummary } from "@/contracts/creator";
import { deleteProject, listProjects } from "@/api/creator";
import { useRouter } from "@/routing/navigation";
import ModelBadges from "@/components/creator/ModelBadges";
import {
  ProjectComposer,
  SCENARIO_OPTIONS,
  CONTENT_TYPE_OPTIONS,
} from "@/components/creator/ProjectComposer";

interface ProjectCardProps {
  project: ProjectSummary;
  onOpen: (id: string) => void;
  onDelete: (project: ProjectSummary) => void;
  formatDate: (dateStr: string) => string;
}

const ProjectCard = memo(function ProjectCard({
  project,
  onOpen,
  onDelete,
  formatDate,
}: ProjectCardProps) {
  var projectScenarioLabel = "未设置";
  if (project.scenario !== undefined) {
    projectScenarioLabel =
      SCENARIO_OPTIONS.find((option) => option.key === project.scenario)
        ?.label ?? project.scenario;
  }
  var projectContentType = "未设置";
  if (project.contentType) {
    projectContentType =
      CONTENT_TYPE_OPTIONS.find((option) => option.key === project.contentType)
        ?.label ?? project.contentType;
  }
  return (
    <div className="surface surface-hover flex min-h-[188px] flex-col p-4">
      <h3 className="mb-2 truncate text-[15px] font-semibold leading-6 text-[var(--color-text-primary)]">
        {project.name}
      </h3>
      <div className="mb-3 min-h-[52px] rounded-md border border-[#f3f1f0] bg-[rgba(43,18,0,0.02)] px-3 py-2">
        {project.description ? (
          <p className="line-clamp-2 text-[13px] leading-5 text-[var(--color-text-secondary)]">
            {project.description}
          </p>
        ) : (
          <p className="text-[13px] leading-5 text-[var(--color-text-tertiary)]">
            暂无项目描述
          </p>
        )}
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="badge border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]">
          视频场景 {projectScenarioLabel}
        </span>
        <span className="badge border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]">
          内容类型 {projectContentType}
        </span>
        <span className="badge border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]">
          画面长宽比 {project.aspectRatio}
        </span>
        <span className="badge border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]">
          图像分辨率 {project.resolution}
        </span>
      </div>
      <div className="mb-4 flex items-center gap-4 text-xs text-[var(--color-text-tertiary)]">
        <p className="flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" />
          创建于 {formatDate(project.createdAt)}
        </p>
        <p className="flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" />
          更新于 {formatDate(project.updatedAt)}
        </p>
      </div>
      <div className="mt-auto flex items-center gap-2 border-t border-[var(--color-border)] pt-3">
        <button
          onClick={() => onOpen(project.projectId)}
          className="btn-primary flex-1 cursor-pointer"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          打开
        </button>
        <button
          onClick={() => onDelete(project)}
          className="btn-primary flex-1 cursor-pointer"
          aria-label={`删除 ${project.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          删除
        </button>
      </div>
    </div>
  );
});

export default function HomePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [composerOpen, setComposerOpen] = useState(false);

  const fetchProjects = useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data.items || []);
    } catch {
      message.error("加载项目列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  const handleOpen = useCallback(
    (id: string) => {
      router.push(`/project/${id}/plan`);
    },
    [router],
  );

  const handleDelete = useCallback(
    (project: ProjectSummary) => {
      Modal.confirm({
        title: "确认删除",
        content: `确定要删除项目「${project.name}」吗？此操作不可撤销。`,
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: true },
        onOk: async () => {
          try {
            await deleteProject(project.projectId);
            message.success("项目已删除");
            fetchProjects();
          } catch {
            message.error("删除项目失败");
          }
        },
      });
    },
    [fetchProjects],
  );

  const formatDate = useCallback((dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }, []);

  return (
    <div className="min-h-full app-shell">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]">
        <div className="page-container flex h-16 items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-accent)] text-white">
              <Film className="h-4 w-4" />
            </div>
            <div>
              <span className="block text-lg font-semibold text-[var(--color-text-primary)]">
                QwenPaw Creator
              </span>
            </div>
          </div>
          <ModelBadges />
        </div>
      </header>

      <main className="page-container py-4">
        <section className="mb-4 rounded-lg border border-[var(--color-border)] bg-[rgba(255,255,255,0.5)] p-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
                我的项目
              </h1>
            </div>
            <button
              onClick={() => setComposerOpen(true)}
              className="btn-primary cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              新建项目
            </button>
          </div>
        </section>

        {loading ? (
          <div className="surface flex items-center justify-center py-28">
            <div className="text-[var(--color-text-secondary)] text-sm">
              加载中...
            </div>
          </div>
        ) : projects.length === 0 ? (
          <div className="surface flex flex-col items-center justify-center px-6 py-28 text-center">
            <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-lg bg-[var(--color-accent-soft)]">
              <Film className="h-7 w-7 text-[var(--color-accent)]" />
            </div>
            <h2 className="mb-8 text-lg font-semibold text-[var(--color-text-primary)]">
              暂无项目
            </h2>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard
                key={project.projectId}
                project={project}
                onOpen={handleOpen}
                onDelete={handleDelete}
                formatDate={formatDate}
              />
            ))}
          </div>
        )}
      </main>

      <ProjectComposer
        open={composerOpen}
        onClose={() => setComposerOpen(false)}
      />
    </div>
  );
}
