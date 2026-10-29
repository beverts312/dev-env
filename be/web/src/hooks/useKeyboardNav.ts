import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { PAGES } from '@/lib/pages'

// The keyboard moves a selection through the rows of the page's tables. Components mark what it
// reads with data attributes, rather than handing it state:
//   data-nav-section            a table (data-collapsed="true" when collapsed)
//     data-nav-collapse          its collapse button; data-nav-search its search box;
//     data-nav-allfilters        its toggle-all-filters button
//     data-nav-row               a row (an issue's has data-key and data-parent-key)
//       data-nav-primary         clicked by enter; data-nav-link opened by o; data-nav-pick toggled by x;
//                                data-nav-star toggled by s;
//       data-nav-action="ready"  clicked by r ("automerge" by u); data-nav-twist opens and closes children
// The selected row gets data-selected="true".
export function useKeyboardNav(onHelp: () => void) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const pos = useRef({ t: 0, r: 0 })
  // read through refs, so a new navigate or onHelp doesn't reset the selection
  const go = useRef(navigate)
  const help = useRef(onHelp)
  useEffect(() => {
    go.current = navigate
    help.current = onHelp
  })

  useEffect(() => {
    pos.current = { t: 0, r: 0 }
    const sections = () => [...document.querySelectorAll<HTMLElement>('main [data-nav-section]')]
    const rows = () => {
      const s = sections()[pos.current.t]
      return s ? [...s.querySelectorAll<HTMLElement>('[data-nav-row]')] : []
    }
    const draw = (scroll = true) => {
      document.querySelectorAll('[data-selected="true"]').forEach((e) => e.removeAttribute('data-selected'))
      const all = rows()
      pos.current.r = Math.max(0, Math.min(pos.current.r, all.length - 1))
      const row = all[pos.current.r]
      if (!row) return
      row.setAttribute('data-selected', 'true')
      if (scroll) row.scrollIntoView({ block: 'nearest' })
    }
    // rows render after their data loads, so select the first once there is one
    const observer = new MutationObserver(() => {
      if (!document.querySelector('[data-selected="true"]')) draw(false)
    })
    const main = document.querySelector('main')
    if (main) observer.observe(main, { childList: true, subtree: true })
    draw(false)

    // a click selects the row clicked
    const onClick = (e: MouseEvent) => {
      const row = (e.target as HTMLElement).closest<HTMLElement>('[data-nav-row]')
      const section = row?.closest<HTMLElement>('[data-nav-section]')
      if (!row || !section) return
      pos.current.t = Math.max(0, sections().indexOf(section))
      pos.current.r = Math.max(0, rows().indexOf(row))
      draw(false)
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement
      // dialogs and open menus keep their own keys
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]')) return
      // typing doesn't trigger keys; escape or enter in the search box goes back to the rows
      if (target.matches('input, textarea, select, [contenteditable="true"]')) {
        if (target.matches('[data-nav-search]') && (e.key === 'Escape' || e.key === 'Enter')) {
          target.blur()
          e.preventDefault()
        }
        return
      }
      // a focused button or link keeps enter and space
      if ((e.key === 'Enter' || e.key === ' ') && target.closest('button, a, [role="radio"]')) return
      const section = sections()[pos.current.t]
      const row = rows()[pos.current.r]
      const click = (el: Element | null | undefined) => {
        if (el instanceof HTMLElement) el.click()
      }
      const page = PAGES.findIndex((p) => p.path === pathname)
      if (e.key === '?') help.current()
      else if (e.key === 't') go.current(PAGES[(page + 1) % PAGES.length].path)
      else if (e.key >= '1' && e.key <= String(PAGES.length)) go.current(PAGES[Number(e.key) - 1].path)
      else if (e.key === '/') section?.querySelector<HTMLElement>('[data-nav-search]')?.focus()
      else if (e.key === 'ArrowDown' || e.key === 'j') pos.current.r++
      else if (e.key === 'ArrowUp' || e.key === 'k') pos.current.r = Math.max(0, pos.current.r - 1)
      else if (e.key === 'm') pos.current = { t: (pos.current.t + 1) % Math.max(1, sections().length), r: 0 }
      else if (e.key === 'c') click(section?.querySelector('[data-nav-collapse]'))
      else if (e.key === 'a') click(section?.querySelector('[data-nav-allfilters]'))
      else if (!row) return
      else if (e.key === 'Enter') click(row.querySelector('[data-nav-primary]'))
      else if (e.key === 'o') {
        const link = row.querySelector<HTMLAnchorElement>('[data-nav-link]')
        if (link) window.open(link.href, '_blank', 'noreferrer')
      } else if (e.key === 'x') click(row.querySelector('[data-nav-pick]'))
      else if (e.key === 's') click(row.querySelector('[data-nav-star]'))
      else if (e.key === 'r') click(row.querySelector('[data-nav-action="ready"]'))
      else if (e.key === 'u') click(row.querySelector('[data-nav-action="automerge"]'))
      else if (e.key === 'ArrowRight' || e.key === 'l') {
        const twist = row.querySelector('[data-nav-twist]')
        if (twist?.getAttribute('aria-expanded') === 'false') click(twist)
      } else if (e.key === 'ArrowLeft' || e.key === 'h') {
        // like a file tree: close an open issue, else move to its parent
        const twist = row.querySelector('[data-nav-twist]')
        if (twist?.getAttribute('aria-expanded') === 'true') click(twist)
        else if (row.dataset.parentKey) {
          const parent = rows().findIndex((x) => x.dataset.key === row.dataset.parentKey)
          if (parent >= 0) pos.current.r = parent
        }
      } else return
      e.preventDefault()
      // let React render what a click changed before selecting
      requestAnimationFrame(() => draw())
    }

    document.addEventListener('keydown', onKey)
    document.addEventListener('click', onClick)
    return () => {
      observer.disconnect()
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('click', onClick)
    }
  }, [pathname])
}
