<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-controls">
          <input
            v-model.number="budget"
            type="range"
            min="0"
            max="200000"
            step="500"
            class="budget-slider"
          />
          <div class="budget-display">
            {{ currencySymbol }}{{ budget.toLocaleString() }}
          </div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.budget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.allocated') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ totalAllocated.toLocaleString() }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.stats.remaining') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ remainingBudget.toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>

      <div class="card recommendations-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.title') }} ({{ recommendations.length }})</h3>
        </div>
        <div v-if="recommendations.length === 0" class="no-data">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table class="recommendations-table">
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.currentStock') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.recommendedQuantity') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in recommendations" :key="rec.item_sku">
                <td><strong>{{ rec.item_sku }}</strong></td>
                <td>{{ rec.item_name }}</td>
                <td>{{ rec.qtyOnHand }}</td>
                <td>{{ rec.forecasted_demand }}</td>
                <td>{{ currencySymbol }}{{ rec.unitCost.toFixed(2) }}</td>
                <td><strong>{{ rec.allocatedQuantity }}</strong></td>
                <td>{{ currencySymbol }}{{ rec.lineCost.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="action-container">
        <button
          @click="placeOrder"
          :disabled="submitting || recommendations.length === 0"
          class="button primary"
        >
          <span v-if="!submitting">{{ t('restocking.placeOrderButton') }}</span>
          <span v-else>{{ t('common.loading') }}</span>
        </button>
      </div>

      <div v-if="submitError" class="error">{{ submitError }}</div>

      <div v-if="submittedOrder" class="success-banner">
        <strong>{{ t('restocking.orderSuccess', {
          orderNumber: submittedOrder.order_number,
          leadTime: submittedOrder.lead_time_days
        }) }}</strong>
        <p style="margin-top: 0.5rem; opacity: 0.9;">{{ t('common.noData') }}</p>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const inventory = ref([])

    const budget = ref(25000)
    const submitting = ref(false)
    const submitError = ref(null)
    const submittedOrder = ref(null)

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        const [forecastsData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory()
        ])
        forecasts.value = forecastsData
        inventory.value = inventoryData
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const inventoryBySku = computed(() => {
      const map = {}
      for (const item of inventory.value) {
        if (!map[item.sku]) {
          map[item.sku] = { qtyOnHand: 0, unitCost: item.unit_cost }
        }
        map[item.sku].qtyOnHand += item.quantity_on_hand
      }
      return map
    })

    const trendPriority = { increasing: 0, stable: 1, decreasing: 2 }

    const recommendations = computed(() => {
      const candidates = forecasts.value
        .map(f => {
          const inv = inventoryBySku.value[f.item_sku] || { qtyOnHand: 0, unitCost: 0 }
          const shortfall = Math.max(0, f.forecasted_demand - inv.qtyOnHand)
          return { ...f, qtyOnHand: inv.qtyOnHand, unitCost: inv.unitCost, shortfall }
        })
        .filter(c => c.shortfall > 0 && c.unitCost > 0)
        .sort((a, b) => {
          const p = trendPriority[a.trend] - trendPriority[b.trend]
          return p !== 0 ? p : b.shortfall - a.shortfall
        })

      let remaining = budget.value
      const result = []
      for (const c of candidates) {
        if (remaining < c.unitCost) continue
        const affordableUnits = Math.floor(remaining / c.unitCost)
        const allocatedQuantity = Math.min(c.shortfall, affordableUnits)
        if (allocatedQuantity <= 0) continue
        const lineCost = Math.round(allocatedQuantity * c.unitCost * 100) / 100
        remaining -= lineCost
        result.push({ ...c, allocatedQuantity, lineCost })
      }
      return result
    })

    const totalAllocated = computed(() =>
      recommendations.value.reduce((sum, r) => sum + r.lineCost, 0)
    )

    const remainingBudget = computed(() => budget.value - totalAllocated.value)

    const placeOrder = async () => {
      try {
        submitting.value = true
        submitError.value = null
        const payload = {
          budget: budget.value,
          items: recommendations.value.map(r => ({
            sku: r.item_sku,
            name: r.item_name,
            quantity: r.allocatedQuantity,
            unit_cost: r.unitCost
          }))
        }
        submittedOrder.value = await api.createRestockOrder(payload)
      } catch (err) {
        submitError.value = 'Failed to submit restocking order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    watch(budget, () => {
      submittedOrder.value = null
    })

    onMounted(loadData)

    return {
      t,
      currencySymbol,
      loading,
      error,
      budget,
      recommendations,
      totalAllocated,
      remainingBudget,
      submitting,
      submitError,
      submittedOrder,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 2rem;
}

.budget-controls {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1.5rem;
}

.budget-slider {
  flex: 1;
  min-width: 200px;
  height: 8px;
  -webkit-appearance: none;
  appearance: none;
  background: #e2e8f0;
  border-radius: 4px;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: box-shadow 0.2s;
}

.budget-slider::-webkit-slider-thumb:hover {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: box-shadow 0.2s;
}

.budget-slider::-moz-range-thumb:hover {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.budget-display {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 150px;
  text-align: right;
}

.recommendations-table {
  table-layout: fixed;
  width: 100%;
}

.action-container {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin: 2rem 0;
}

.button {
  padding: 0.75rem 2rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.button.primary {
  background: #3b82f6;
  color: white;
}

.button.primary:hover:not(:disabled) {
  background: #2563eb;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.success-banner {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-left: 4px solid #10b981;
  border-radius: 8px;
  padding: 1rem;
  margin-top: 1.5rem;
  color: #047857;
}

.no-data {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
</style>
