import type { InstanceResult } from '../types'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuBadge,
} from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

interface Props {
  instances: InstanceResult[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function scoreBadgeClass(score: number) {
  if (score >= 0.8) return 'bg-green-900/80 text-green-300'
  if (score >= 0.5) return 'bg-yellow-900/80 text-yellow-300'
  return 'bg-red-900/80 text-red-300'
}

export function AppSidebar({ instances, selectedId, onSelect }: Props) {
  const sorted = [...instances].sort((a, b) => b.total_score - a.total_score)

  return (
    <Sidebar collapsible="none" className="border-r">
      <SidebarHeader className="px-4 py-3">
        <h2 className="text-xs font-semibold text-sidebar-foreground/70 uppercase tracking-wider">
          Instances ({instances.length})
        </h2>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup className="p-0">
          <SidebarGroupContent>
            <SidebarMenu>
              {sorted.map(inst => (
                <SidebarMenuItem key={inst.instance_id}>
                  <SidebarMenuButton
                    isActive={selectedId === inst.instance_id}
                    onClick={() => onSelect(inst.instance_id)}
                    className="h-auto py-2.5 px-3 flex-col items-start gap-0.5"
                    tooltip={inst.instance_id}
                  >
                    <span className="text-sm font-medium truncate w-full">
                      {inst.instance_id}
                    </span>
                    <span className="text-xs text-sidebar-foreground/50">
                      {inst.stages.filter(s => s.status === 'passed').length}/{inst.stages.length} stages passed
                    </span>
                  </SidebarMenuButton>
                  <SidebarMenuBadge
                    className={cn(
                      'rounded-md px-1.5 py-0.5 text-[10px] font-semibold',
                      scoreBadgeClass(inst.total_score)
                    )}
                  >
                    {(inst.total_score * 100).toFixed(0)}%
                  </SidebarMenuBadge>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
