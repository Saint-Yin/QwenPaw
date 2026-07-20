import { useState, useEffect } from "react";
import { Modal, Input, Tag, Button, message, Spin } from "antd";
import { ThunderboltOutlined, PictureOutlined } from "@ant-design/icons";
import { displayMediaUrl } from "@/lib/mediaUrl";

const QUICK_OPTIONS = [
  { label: "三视图", value: "三视图，正面/侧面/背面设计参考" },
  { label: "表情", value: "表情变化，多种面部表情" },
  { label: "姿态", value: "姿态参考，站姿/坐姿" },
  { label: "动作", value: "动态动作姿势" },
  { label: "服装", value: "服装变体，不同穿搭" },
];

interface NewAppearanceModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (
    refDescription: string,
    prompt: string,
    imageUrl: string,
  ) => Promise<void>;
  assetName: string;
  projectId: string;
  assetId: string;
  referenceImageUrl?: string;
  onGeneratePrompt?: (refDescription: string) => Promise<string>;
  onGenerateImage?: (prompt: string) => Promise<string>;
}

type Step = "input" | "prompt" | "preview";

export default function NewAppearanceModal({
  open,
  onClose,
  onConfirm,
  assetName,
  projectId,
  assetId,
  referenceImageUrl,
  onGeneratePrompt,
  onGenerateImage,
}: NewAppearanceModalProps) {
  const [step, setStep] = useState<Step>("input");
  const [refDescription, setRefDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingImage, setLoadingImage] = useState(false);

  // 当关键 props 变化时重置状态
  useEffect(() => {
    setStep("input");
    setRefDescription("");
    setPrompt("");
    setImageUrl("");
    setLoading(false);
    setLoadingImage(false);
  }, [assetId, projectId, referenceImageUrl]);

  const handleClose = () => {
    setStep("input");
    setRefDescription("");
    setPrompt("");
    setImageUrl("");
    setLoading(false);
    setLoadingImage(false);
    onClose();
  };

  const handleGeneratePrompt = async () => {
    if (!refDescription.trim()) {
      message.warning("请输入需求描述");
      return;
    }
    setLoading(true);
    try {
      const generated = onGeneratePrompt
        ? await onGeneratePrompt(refDescription)
        : `${assetName}，${refDescription}`;
      setPrompt(generated);
      setStep("prompt");
    } catch (err) {
      message.error(`生成失败：${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateImage = async () => {
    if (!prompt.trim()) {
      message.warning("Prompt 不能为空");
      return;
    }
    setLoadingImage(true);
    try {
      const generated = onGenerateImage
        ? await onGenerateImage(prompt)
        : referenceImageUrl || "";
      if (!generated) throw new Error("生成任务尚未返回图片，请稍后重试");
      setImageUrl(generated);
      setStep("preview");
    } catch (err) {
      message.error(`生成失败：${(err as Error).message}`);
    } finally {
      setLoadingImage(false);
    }
  };

  const handleConfirm = async () => {
    try {
      await onConfirm(refDescription, prompt, imageUrl);
      handleClose();
    } catch (err) {
      message.error(`保存失败：${(err as Error).message}`);
    }
  };

  const handleCancel = () => {
    handleClose();
  };

  const renderContent = () => {
    switch (step) {
      case "input":
        return (
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium">需求描述</label>
              <Input
                value={refDescription}
                onChange={(e) => setRefDescription(e.target.value)}
                placeholder="描述你想要的形象，如：3/4侧面全身像"
                size="large"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium">快捷选项</label>
              <div className="flex flex-wrap gap-2">
                {QUICK_OPTIONS.map((option) => (
                  <Tag
                    key={option.label}
                    className="cursor-pointer"
                    onClick={() => setRefDescription(option.value)}
                  >
                    {option.label}
                  </Tag>
                ))}
              </div>
            </div>
          </div>
        );

      case "prompt":
        return (
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium">需求描述</label>
              <div className="rounded-lg bg-gray-50 p-2 text-sm">
                {refDescription}
              </div>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium">
                生成的 Prompt（可编辑）
              </label>
              <Input.TextArea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="Prompt"
              />
            </div>
          </div>
        );

      case "preview":
        return (
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium">需求描述</label>
              <div className="rounded-lg bg-gray-50 p-2 text-sm">
                {refDescription}
              </div>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium">
                生成的图片
              </label>
              <div className="overflow-hidden rounded-lg border">
                <img
                  src={displayMediaUrl(imageUrl)}
                  alt="预览"
                  className="w-full object-contain"
                  onError={(e) => {
                    e.currentTarget.src = "/placeholder-error.png";
                    message.error("图片加载失败，请重试");
                  }}
                />
              </div>
            </div>
          </div>
        );
    }
  };

  const renderFooter = () => {
    switch (step) {
      case "input":
        return (
          <>
            <Button onClick={handleCancel}>取消</Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={loading}
              onClick={handleGeneratePrompt}
              disabled={!refDescription.trim()}
            >
              AI 生成 Prompt
            </Button>
          </>
        );

      case "prompt":
        return (
          <>
            <Button onClick={() => setStep("input")}>上一步</Button>
            <Button
              type="primary"
              icon={<PictureOutlined />}
              loading={loadingImage}
              onClick={handleGenerateImage}
              disabled={!prompt.trim()}
            >
              生成图片
            </Button>
          </>
        );

      case "preview":
        return (
          <>
            <Button onClick={handleCancel}>取消</Button>
            <Button type="primary" onClick={handleConfirm}>
              确认添加
            </Button>
          </>
        );
    }
  };

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      title={`为"${assetName}"新建形象`}
      width={560}
      footer={renderFooter()}
    >
      <div className="py-4">
        {loading || loadingImage ? (
          <div className="flex h-48 items-center justify-center">
            <Spin
              size="large"
              tip={loadingImage ? "生成图片中..." : "生成 Prompt 中..."}
            />
          </div>
        ) : (
          renderContent()
        )}
      </div>
    </Modal>
  );
}
