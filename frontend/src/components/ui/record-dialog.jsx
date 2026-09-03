// Reutiliza los formularios existentes como fichas de página, sin portal/modal.
import { createContext, useContext, cloneElement } from 'react'
import * as Modal from './dialog'
export const RecordMode = createContext(false)
const CloseContext = createContext(() => {})
export function Dialog({open,onOpenChange,children,...props}) {
  const inline=useContext(RecordMode)
  return inline ? (open?<CloseContext.Provider value={()=>onOpenChange?.(false)}>{children}</CloseContext.Provider>:null) : <Modal.Dialog open={open} onOpenChange={onOpenChange} {...props}>{children}</Modal.Dialog>
}
export function DialogContent({children,className='',...props}) {
  const inline=useContext(RecordMode)
  return inline?<section className={'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6 '+className.replace(/max-w-\S+|max-h-\S+|overflow-y-auto/g,'')}>{children}</section>:<Modal.DialogContent className={className} {...props}>{children}</Modal.DialogContent>
}
export function DialogTitle({children,...props}) {const inline=useContext(RecordMode);return inline?<h2 className="text-xl font-semibold mb-2">{children}</h2>:<Modal.DialogTitle {...props}>{children}</Modal.DialogTitle>}
export function DialogDescription({children,...props}) {const inline=useContext(RecordMode);return inline?<p className="text-sm mb-4 text-[var(--color-text-secondary)]">{children}</p>:<Modal.DialogDescription {...props}>{children}</Modal.DialogDescription>}
export function DialogClose({children,asChild,...props}) {const inline=useContext(RecordMode);const close=useContext(CloseContext);return inline?(asChild?cloneElement(children,{onClick:e=>{children.props.onClick?.(e);if(!e.defaultPrevented)close()}}):<button onClick={close} {...props}>{children}</button>):<Modal.DialogClose asChild={asChild} {...props}>{children}</Modal.DialogClose>}
