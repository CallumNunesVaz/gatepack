import { ProjectProvider } from './state/project';
import { SelectionProvider } from './selection/bus';
import { Shell } from './shell/Shell';

export function App() {
  return (
    <ProjectProvider>
      <SelectionProvider>
        <Shell />
      </SelectionProvider>
    </ProjectProvider>
  );
}
