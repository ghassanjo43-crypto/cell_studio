// Hover interaction plumbing. A React context carries the "onHover" callback into the
// scene so any clickable structure can raise hover events (for the DOM tooltip)
// without threading a prop through every component. Clicking still uses each
// component's existing onSelect.

import type { ThreeEvent } from "@react-three/fiber";
import { createContext, useContext, useMemo } from "react";
import type { ObjectId } from "../inspect";

export type HoverFn = (id: ObjectId | null, x?: number, y?: number) => void;

const HoverContext = createContext<HoverFn>(() => {});

export const HoverProvider = HoverContext.Provider;

export function useHover(): HoverFn {
  return useContext(HoverContext);
}

type PointerHandlers = {
  onPointerOver: (e: ThreeEvent<PointerEvent>) => void;
  onPointerMove: (e: ThreeEvent<PointerEvent>) => void;
  onPointerOut: (e: ThreeEvent<PointerEvent>) => void;
};

/** Pointer handlers that report hover of structure `id` (with cursor position). */
export function useHoverHandlers(id: ObjectId): PointerHandlers {
  const onHover = useHover();
  return useMemo<PointerHandlers>(
    () => ({
      onPointerOver: (e) => {
        e.stopPropagation();
        onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY);
      },
      onPointerMove: (e) => {
        e.stopPropagation();
        onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY);
      },
      onPointerOut: (e) => {
        e.stopPropagation();
        onHover(null);
      },
    }),
    [id, onHover],
  );
}
