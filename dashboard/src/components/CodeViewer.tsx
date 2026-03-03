import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ChevronUp, FileCode } from 'lucide-react'

interface Props {
  filename: string
  code: string
}

export function CodeViewer({ filename, code }: Props) {
  const [open, setOpen] = useState(true)
  const lineCount = code.split('\n').length

  return (
    <Card className="overflow-hidden mb-3">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center justify-between px-4 py-2.5 bg-secondary/50 hover:bg-secondary transition-colors text-left">
            <div className="flex items-center gap-2">
              <FileCode className="h-4 w-4 text-primary" />
              <span className="font-mono text-sm text-primary">{filename}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{lineCount} lines</span>
              {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
            </div>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="overflow-x-auto">
            <pre className="p-4 text-sm leading-relaxed">
              <code>{code.split('\n').map((line, i) => (
                <div key={i} className="flex">
                  <span className="text-muted-foreground select-none w-10 text-right pr-4 shrink-0">{i + 1}</span>
                  <span className="text-foreground">{line}</span>
                </div>
              ))}</code>
            </pre>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
