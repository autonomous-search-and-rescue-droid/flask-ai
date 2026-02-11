
import cv2
import numpy as np
import heapq
import math

class DynamicAStar:
    def __init__(self, map_path):
        self.map_img = cv2.imread(map_path, cv2.IMREAD_GRAYSCALE)
        if self.map_img is None:
            raise ValueError(f"Could not load map from {map_path}")
        
        # Binarize map: White (255) is free, Black (0) is obstacle
        # We'll treat anything > 200 as free space based on analysis
        _, self.grid = cv2.threshold(self.map_img, 200, 255, cv2.THRESH_BINARY)
        self.height, self.width = self.grid.shape
        
        self.s_start = None
        self.s_goal = None
        self.s_last = None
        self.k_m = 0
        self.U = [] # Priority Queue
        self.rhs = {}
        self.g = {}
        
    def get_valid_start_goal(self):
        # Use connected components to find the largest walkable area
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(self.grid, connectivity=8)
        
        # stats[0] is usually background (label 0, black), we want largest white area
        # Slicing [1:] to skip background, finding max area
        if num_labels < 2:
            raise ValueError("No walkable area found!")
            
        largest_label_idx = np.argmax(stats[1:, cv2.CC_STAT_AREA]) + 1
        
        # Create a mask for the largest component
        mask = (labels == largest_label_idx)
        
        # Get all coordinates in this component
        y_indices, x_indices = np.where(mask)
        
        if len(y_indices) == 0:
             raise ValueError("Largest component has no points?")

        # Pick two points far apart: Top-most-left and Bottom-most-right
        # Indices are sorted by y then x usually
        start = (y_indices[0], x_indices[0])
        goal = (y_indices[-1], x_indices[-1])
        
        return start, goal

    def init_d_star(self, start, goal):
        self.s_start = start
        self.s_goal = goal
        self.s_last = self.s_start
        self.k_m = 0
        self.U = []
        self.rhs = {}
        self.g = {}
        
        for i in range(self.height):
            for j in range(self.width):
                self.rhs[(i, j)] = float('inf')
                self.g[(i, j)] = float('inf')
                
        self.rhs[self.s_goal] = 0
        heapq.heappush(self.U, (self.calculate_key(self.s_goal), self.s_goal))

    def calculate_key(self, s):
        min_g_rhs = min(self.g.get(s, float('inf')), self.rhs.get(s, float('inf')))
        return (min_g_rhs + self.heuristic(self.s_start, s) + self.k_m, min_g_rhs)

    def heuristic(self, a, b):
        # Euclidean distance
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def get_neighbors(self, s):
        # 8-connected grid
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1), 
                      (-1, -1), (-1, 1), (1, -1), (1, 1)]
        
        for dx, dy in directions:
            nx, ny = s[0] + dx, s[1] + dy
            
            if 0 <= nx < self.height and 0 <= ny < self.width:
                # Check for obstacle
                if self.grid[nx, ny] > 0: # > 0 means free (white is 255)
                    neighbors.append((nx, ny))
                    
        return neighbors

    def update_vertex(self, u):
        if u != self.s_goal:
            min_rhs = float('inf')
            for s_prime in self.get_neighbors(u):
                # cost is distance (1 for straight, sqrt(2) for diagonal)
                dist = math.hypot(u[0] - s_prime[0], u[1] - s_prime[1])
                min_rhs = min(min_rhs, self.g.get(s_prime, float('inf')) + dist)
            self.rhs[u] = min_rhs
            
        # Remove u from U if it exists (simplified by just pushing new and ignoring old)
        # In a real efficient implementation, we'd have a handle to update priority
        # Here we deal with potential duplicates in compute_shortest_path
        
        if self.g.get(u, float('inf')) != self.rhs.get(u, float('inf')):
            heapq.heappush(self.U, (self.calculate_key(u), u))

    def compute_shortest_path(self):
        while self.U and (self.U[0][0] < self.calculate_key(self.s_start) or \
                          self.rhs.get(self.s_start, float('inf')) != self.g.get(self.s_start, float('inf'))):
            k_old, u = heapq.heappop(self.U)
            
            # Filter out stale keys
            if k_old < self.calculate_key(u):
                 continue
                 
            k_new = self.calculate_key(u)
            
            if k_old < k_new:
                heapq.heappush(self.U, (k_new, u))
            elif self.g.get(u, float('inf')) > self.rhs.get(u, float('inf')):
                self.g[u] = self.rhs[u]
                for s in self.get_neighbors(u):
                    self.update_vertex(s)
            else:
                g_old = self.g[u]
                self.g[u] = float('inf')
                for s in self.get_neighbors(u) + [u]:
                    self.update_vertex(s)
                    
    def get_path(self):
        path = []
        curr = self.s_start
        path.append(curr)
        
        while curr != self.s_goal:
            min_cost = float('inf')
            next_node = None
            
            for s_prime in self.get_neighbors(curr):
                dist = math.hypot(curr[0] - s_prime[0], curr[1] - s_prime[1])
                cost = self.g.get(s_prime, float('inf')) + dist
                
                if cost < min_cost:
                    min_cost = cost
                    next_node = s_prime
            
            if next_node is None:
                break
                
            path.append(next_node)
            curr = next_node
            
            if len(path) > self.height * self.width: # Prevent infinite loop
                break
                
        return path
    
    def draw_path(self, path, output_path="path_result.png"):
        output_img = cv2.cvtColor(self.map_img, cv2.COLOR_GRAY2BGR)
        
        # Draw Start (Green) and Goal (Red)
        if self.s_start:
             cv2.circle(output_img, (self.s_start[1], self.s_start[0]), 5, (0, 255, 0), -1)
        if self.s_goal:
             cv2.circle(output_img, (self.s_goal[1], self.s_goal[0]), 5, (0, 0, 255), -1)

        # Draw Path (Blue)
        for i in range(len(path) - 1):
            p1 = (path[i][1], path[i][0])
            p2 = (path[i+1][1], path[i+1][0])
            cv2.line(output_img, p1, p2, (255, 0, 0), 2)
            
        cv2.imwrite(output_path, output_img)
        print(f"Path saved to {output_path}")
# ... (rest of class)

def main():
    map_file = "d:/Admin_Panel/Backend/map/map.png" # Using absolute path based on user context
    
    try:
        planner = DynamicAStar(map_file)
        start_node, goal_node = planner.get_valid_start_goal()
        print(f"Auto-selected valid points in largest component:")
        print(f"Start: {start_node}")
        print(f"Goal:  {goal_node}")
    except ValueError as e:
        print(e)
        return

    print(f"Planning from {start_node} to {goal_node}")
    
    planner.init_d_star(start_node, goal_node)
    planner.compute_shortest_path()
    path = planner.get_path()
    
    if len(path) > 1:
        print(f"Path found with {len(path)} steps.")
        planner.draw_path(path)
    else:
        print("No path found.")

if __name__ == "__main__":
    main()
