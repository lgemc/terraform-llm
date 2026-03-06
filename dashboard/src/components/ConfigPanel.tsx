import type { BenchmarkResults } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, Settings } from 'lucide-react'
import { useState } from 'react'

interface Props {
  results: BenchmarkResults
}

export function ConfigPanel({ results }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  const hasConfig = results.model_config || results.eval_config || results.execution_config

  if (!hasConfig) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card className="mb-4">
        <CollapsibleTrigger className="w-full">
          <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings className="h-4 w-4" />
                <CardTitle className="text-sm">Run Configuration</CardTitle>
                {results.config_file && (
                  <Badge variant="outline" className="text-xs">
                    {results.config_file.split('/').pop()}
                  </Badge>
                )}
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? '' : '-rotate-90'}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="pt-0 space-y-4">
            {/* Model Configuration */}
            {results.model_config && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">Model Configuration</h4>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Model:</span>
                    <span className="ml-2 font-mono">{results.model_config.model}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Agent Type:</span>
                    <span className="ml-2">{results.model_config.agent_type}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Temperature:</span>
                    <span className="ml-2 font-mono">{results.model_config.temperature}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Max Tokens:</span>
                    <span className="ml-2 font-mono">{results.model_config.max_tokens}</span>
                  </div>
                  {results.model_config.multiturn && (
                    <>
                      <div>
                        <span className="text-muted-foreground">Multiturn:</span>
                        <Badge variant="outline" className="ml-2 text-xs">Enabled</Badge>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Max Iterations:</span>
                        <span className="ml-2 font-mono">{results.model_config.max_multiturn_iterations}</span>
                      </div>
                    </>
                  )}
                  {results.model_config.agent_type === 'tool-enabled' && (
                    <>
                      <div>
                        <span className="text-muted-foreground">Max Tool Iterations:</span>
                        <span className="ml-2 font-mono">{results.model_config.max_tool_iterations}</span>
                      </div>
                      {results.model_config.docs_index_path && (
                        <div className="col-span-2">
                          <span className="text-muted-foreground">Docs Index:</span>
                          <span className="ml-2 font-mono text-xs">{results.model_config.docs_index_path}</span>
                        </div>
                      )}
                    </>
                  )}
                  {results.model_config.reasoning_effort && (
                    <div>
                      <span className="text-muted-foreground">Reasoning Effort:</span>
                      <span className="ml-2">{results.model_config.reasoning_effort}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Evaluation Configuration */}
            {results.eval_config && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">Evaluation Configuration</h4>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Run Apply:</span>
                    <Badge variant="outline" className="ml-2 text-xs">
                      {results.eval_config.run_apply ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Use Docker:</span>
                    <Badge variant="outline" className="ml-2 text-xs">
                      {results.eval_config.use_docker ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                  {results.eval_config.use_docker && (
                    <>
                      <div>
                        <span className="text-muted-foreground">Backend:</span>
                        <span className="ml-2 capitalize">{results.eval_config.backend}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Terraform Image:</span>
                        <span className="ml-2 font-mono text-xs">{results.eval_config.terraform_image}</span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-muted-foreground">
                          {results.eval_config.backend === 'localstack' ? 'LocalStack' : 'Moto'} Image:
                        </span>
                        <span className="ml-2 font-mono text-xs">
                          {results.eval_config.backend === 'localstack'
                            ? results.eval_config.localstack_image
                            : results.eval_config.moto_image}
                        </span>
                      </div>
                    </>
                  )}
                  <div>
                    <span className="text-muted-foreground">Timeouts:</span>
                    <span className="ml-2 font-mono text-xs">
                      init: {results.eval_config.init_timeout}s,
                      plan: {results.eval_config.plan_timeout}s,
                      apply: {results.eval_config.apply_timeout}s
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Execution Configuration */}
            {results.execution_config && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">Execution Configuration</h4>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Parallel Workers:</span>
                    <span className="ml-2 font-mono">{results.execution_config.parallel}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Skip Generation:</span>
                    <Badge variant="outline" className="ml-2 text-xs">
                      {results.execution_config.skip_generation ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                </div>
              </div>
            )}

            {/* Output Directory */}
            {results.output_dir && (
              <div>
                <span className="text-xs text-muted-foreground">Output Directory:</span>
                <span className="ml-2 text-xs font-mono">{results.output_dir}</span>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
