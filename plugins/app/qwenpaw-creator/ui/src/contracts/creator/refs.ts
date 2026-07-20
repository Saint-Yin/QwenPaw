export interface RefSearchItem {
  ref: string;
  name: string;
  type: 'section' | 'unit' | 'asset' | 'artifact';
  version?: string;
  thumbnailUrl?: string;
  url?: string;
  createdAt?: string;
  uiLocator: Record<string, string>;
}

export interface ResolvedRef extends RefSearchItem {
  mediaType?: string;
  checksum?: string;
  logicalAssetId?: string;
  assetVersionId?: string;
  slotId?: string;
  artifactVersionId?: string;
}
