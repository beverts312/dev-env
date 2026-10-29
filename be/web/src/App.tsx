import { BrowserRouter, Route, Routes } from 'react-router'

import { Layout } from '@/components/Layout'
import { Config } from '@/pages/Config'
import { MyPrs } from '@/pages/MyPrs'
import { NotFound } from '@/pages/NotFound'
import { Reviews } from '@/pages/Reviews'
import { Usage } from '@/pages/Usage'
import { Work } from '@/pages/Work'
import { Workspaces } from '@/pages/Workspaces'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Work />} />
          <Route path="prs" element={<MyPrs />} />
          <Route path="reviews" element={<Reviews />} />
          <Route path="workspaces" element={<Workspaces />} />
          <Route path="usage" element={<Usage />} />
          <Route path="config" element={<Config />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
